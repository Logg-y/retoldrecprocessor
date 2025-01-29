import typing
import struct
import io
import os
import json
import zlib
import configparser
import traceback
import datetime
import xmb
import re
from xml.etree import ElementTree as ET

RECORDED_GAME_MAX_DECOMPRESS_SIZE = 150*1024*1024
LOGFILE = "_recprocessor.log"
ILLEGAL_FILENAME_CHARACTERS = "/\\<>:|?\""

def decompressl33tZlib(stream: typing.BinaryIO, maxSize=0) -> typing.BinaryIO:
    "Decompress up to maxSize bytes of a l33t-zlib compressed file, returning a file-like object of decompressed data"
    stream.seek(0x10d)
    compressedLength = struct.unpack("<i", stream.read(4))[0]
    header = stream.read(4)
    if header != b"l33t":
        raise ValueError(f"Bad l33t-zlib header: {header.decode(errors='replace')}")
    decompress = zlib.decompressobj()
    origDataLength = struct.unpack("<i", stream.read(4))[0]
    return io.BytesIO(decompress.decompress(stream.read(compressedLength), maxSize))

def readInt32(stream: typing.BinaryIO) -> int:
    return struct.unpack("<i", stream.read(4))[0]

def readUtf16(stream: typing.BinaryIO) -> str:
    length = readInt32(stream)
    return stream.read(length*2).decode("utf16")
    
# Navigating the embedded two letter coded object tree.
# I didn't realise that this was actually part of the legacy game format too and I could have saved many hours looking at existing tools that worked on that...
# This (somewhat sloppy) code is what I came up with while working out how it fit together
# My later, maybe cleaner, typescript impl: https://github.com/erin-fitzpatric/next-aom-gg/blob/main/src/server/recParser/hierarchy.ts
    

# Objects with substructures that we want to try and parse out.
# Due to reuse of the two letter codes it matters what the parent is.
# "BP":"PL" in here means "parse BP as something with substructures if it's a child of PL"
# None as a parent will always try to parse as container whenever the two letter code is encountered

# TN:J1 is technically a substructure, but I have absolutely no idea what is going on inside it - it doesn't follow on at all!
# CT is too, but it's just causing errors and I don't care about its contents

# This list works and I was using it when looking around
#has_substructure_given_parent = {"BG":None, "GM":None, "J1":None, "PL":"J1", "T3":"TN", "BP":"PL", "KB":None, "MP":"BG", "GD":"GM"}
# This is all the rec renaming process needs
has_substructure_given_parent = {"BG":None, "J1":None, "PL":"J1", "BP":"PL", "MP":None, "GM":None, "GD":"GM"}

SCAN_MAXIMUM = 50
DEBUG = False

class ScanFailureError(Exception):
    pass

def scanForSensibleTwoLetterCodeAndLength(stream: typing.BinaryIO, maxDataLength=None):
    #print(f"Scan at {stream.tell()}")
    unk = b""
    for x in range(0, SCAN_MAXIMUM):
        bad = False
        thisTwoLetterCode = "\x00\x00"
        try:
            thisTwoLetterCode = stream.read(2).decode("ascii")
        except Exception:
            bad = True
        for char in thisTwoLetterCode:
            if ord(char) < 32:
                bad = True
                break
        thisLength = struct.unpack("<I", stream.read(4))[0]
        if maxDataLength is not None and thisLength > maxDataLength:
            bad = True
        if bad:
            stream.seek(stream.tell() - 6)
            unk += stream.read(1)
            continue
        if len(unk) > 0:
            if DEBUG: print(f"Scan search rejected {len(unk)} positions")
        return (thisTwoLetterCode, thisLength, unk)
    msg = f"Failed to find sensible two letter code and length at {stream.tell()}"
    stream.seek(stream.tell()-SCAN_MAXIMUM)
    raise ScanFailureError(msg)

class HierarchyTableEntry:
    def __init__(self, stream: typing.BinaryIO, twoLetterCode: str, lengthBytes: int, preUnknown: bytes):
        self.twoLetterCode = twoLetterCode
        self.lengthBytes = lengthBytes
        self.data = stream.read(self.lengthBytes)
        self.preUnknown = preUnknown
        self.postUnknown = b""
    
class HierarchyCollection:
    def __init__(self, stream: typing.BinaryIO, preUnknown=b"", twoLetterCode=None, lengthBytes=None):
        self.preUnknown = preUnknown
        self.postUnknown = b""
        if twoLetterCode is None or lengthBytes is None:
            twoLetterCode, lengthBytes, self.unkBeforeData = scanForSensibleTwoLetterCodeAndLength(stream)
        else:
            self.unkBeforeData = b""
        self.twoLetterCode = twoLetterCode
        self.lengthBytes = lengthBytes
        self.startPos = stream.tell()
        if DEBUG: print(f"Entry collection {self.twoLetterCode} has total length {self.lengthBytes}, unkBeforeData = {self.unkBeforeData}, start reading entries at {stream.tell()}")
        self.entries = []
        bytesLeft = self.lengthBytes
        while 1:
            try:
                twoLetterCode, lengthBytes, thisUnk = scanForSensibleTwoLetterCodeAndLength(stream, bytesLeft)
            except ScanFailureError:
                if DEBUG: print(f"Scan failed at {stream.tell()}, put all {bytesLeft} bytes into last post unknown...")
                self.entries[-1].postUnknown += stream.read(bytesLeft)
                return
            if twoLetterCode in has_substructure_given_parent and (has_substructure_given_parent[twoLetterCode] is None or self.twoLetterCode == has_substructure_given_parent[twoLetterCode]):
                if DEBUG: print(f"Enter substructure for {twoLetterCode} with parent {self.twoLetterCode}")
                self.entries.append(HierarchyCollection(stream, thisUnk, twoLetterCode, lengthBytes))
            else:
                thisEntry = HierarchyTableEntry(stream, twoLetterCode, lengthBytes, thisUnk)
                self.entries.append(thisEntry)
                if DEBUG: print(f"Read collection entry {len(self.entries)} {thisEntry.twoLetterCode} with {thisEntry.lengthBytes} bytes of data, finishing at {stream.tell()}")
            bytesLeft = self.lengthBytes - (stream.tell() - self.startPos)
            #if DEBUG: print(f"{bytesLeft} bytes left")
            if bytesLeft < 0:
                raise ValueError(f"{self.twoLetterCode} read {-1*bytesLeft} bytes too many at {stream.tell()}")
            if bytesLeft == 0:
                if DEBUG: print(f"Stop: reached target length exactly")
                return
            if bytesLeft < 6:
                self.entries[-1].postUnknown += stream.read(bytesLeft)
                return
            else:
                #print(f"Continue: {bytesLeft} bytes of data left")
                pass
    def find(self, target: typing.Union[str, typing.List[str]]):
        if isinstance(target, str):
            return self.find([target])
        thisTarget = target[0]
        matching = []
        for entry in self.entries:
            if entry.twoLetterCode == thisTarget:
                if len(target) > 1:
                    if not hasattr(entry, "find"):
                        raise ValueError(f"Subitem {entry.twoLetterCode} was not parsed for substructures")
                    matching += entry.find(target[1:])
                else:
                    matching.append(entry)
        return matching
    
def tryParsingHierarchy(stream: typing.BinaryIO) -> HierarchyCollection:
    if stream.read(2) != b"BG":
        raise ValueError("Missing BG top level container")
    stream.seek(stream.tell()-2)
    collection = HierarchyCollection(stream, twoLetterCode="BG")
    return collection

def parseMetadata(hierarchy: HierarchyCollection) -> typing.Dict[str, typing.Any]:
    "Process a decompressed recorded game file, returning a dict of the metadata array"
    # For now I feel like the safest assumption I can make for the file format is
    # that the keys are written in the same order
    # Vs AI games don't seem to have the same data in them!
    keyContainer = hierarchy.find(["MP", "ST"])
    if len(keyContainer) != 1:
        raise ValueError(f"Found {len(keyContainer)} metadata entries (wanted 1). Recordings of single player games do not have this, and this renamer will not work on them")
    stream = io.BytesIO(keyContainer[0].data)
    # unk 4 bytes at the start
    stream.read(4)
    numkeys = readInt32(stream)
    if numkeys > 5000:
        raise ValueError(f"Failed num keys sanity check ({numkeys}). Something likely went wrong.")
    metadata = {}
    for x in range(0, numkeys):
        keyName = readUtf16(stream)
        keyType = readInt32(stream)
        keyValue: typing.Any = None
        if keyType == 1:
            # Also assuming int, unknown how it differs from 2
            # Used for gameplayer0rating, could be uint32?
            keyValue = readInt32(stream)
            if keyValue != 0:
                print(f"Key {keyName} type {keyType} has nonzero value {keyValue}")
        elif keyType == 2:
            # Looks very much like signed int32
            keyValue = readInt32(stream)
        elif keyType == 3:
            # Only gamesyncstate uses this.
            # I have no idea how to interpret its 8 bytes, whether they're useful in any way, or how to represent them in json, so ignoring it for now
            stream.read(8)
            keyValue = None
        elif keyType == 4:
            # Unknown, only case I've seen has a data area of two bytes which are both nulls
            keyValue = struct.unpack("<h", stream.read(2))[0]
            if keyValue != 0:
                print(f"Key {keyName} type {keyType} has nonzero value {keyValue}")
        elif keyType == 6:
            # Assuming bool
            keyValue = struct.unpack("<?", stream.read(1))[0]
        elif keyType == 10:
            # String, formatted the same way as the keynames
            keyValue = readUtf16(stream)
        else:
            raise ValueError(f"Metadata key {keyName} near offset {hex(stream.tell())} has unknown type {keyType}")
        
        if keyValue is not None:
            metadata[keyName] = keyValue
    return metadata
    
def parseXMB(filepath: str, hierarchy: HierarchyCollection, output=False) -> typing.Dict[str, ET.Element]:
    global config
    containers = hierarchy.find(["GM", "GD", "gd"])
    out = {}
    # TODO this parses the entire XMB content of the file, the bulk of which is of no interest here
    for container in containers:
        stream = io.BytesIO(container.data)
        stream.read(1) #unknown
        numFiles = struct.unpack("<I", stream.read(4))[0]
        #log(f"Number of files {numFiles} at {stream.tell()}")
        for fileIndex in range(0, numFiles):
            if numFiles == 1:
                inheritedName = None
            else:
                # read two strings
                extraStrings = []
                for stringIndex in range(0, 2):
                    length = struct.unpack("<I", stream.read(4))[0]
                    #print(f"read extra string length {length} at {stream.tell()}")
                    string = stream.read(length*2).decode("utf-16-le")
                    extraStrings.append(string)
                inheritedName = extraStrings[1]
            
        
            parsed = xmb.parseXMBStream(stream)
            xmlName = parsed.getroot().tag
            if inheritedName is not None:
                xmlName = os.path.basename(inheritedName)
            if output:
                targetDir = filepath+"_xml"
                if not os.path.isdir(targetDir):
                    os.mkdir(targetDir)
                with open(os.path.join(targetDir, f"{xmlName}.xml"), "w") as f:
                    f.write(ET.tostring(parsed.getroot()).decode("utf8"))
            out[xmlName] = parsed
            #log(f"Found xmb: {xmlName}")
        
        #if stream.read(1) != b"g":
        #    # We'd probably expect this to be the case on the last entry
        #    if x != numXmbs-1:
        #        raise ValueError(f"Abort at {stream.tell()}: parsed xmb does not end on 'g' byte")
        #    stream.seek(stream.tell()-1)
        #    break        
        #stream.seek(stream.tell()+6)
    #print(f"Finished at {stream.tell()} = {hex(stream.tell())}")
    return out

def renameRec(filepath: str, metadata: typing.Dict[str, typing.Any], hierarchy: HierarchyCollection):
    global config
    nameTemplate = config.get("rename", "RenameFormat")
    playerTemplate = config.get("rename", "RenameFormatPlayer")
    playersByTeam = {}
    playerGodNames = {}
    xmbs = None
    for playerIndex in range(1, metadata["gamenumplayers"]+1):
        thisTeam = metadata[f"gameplayer{playerIndex}teamid"]
        thisName = metadata[f"gameplayer{playerIndex}name"]
        thisGodID = metadata[f"gameplayer{playerIndex}civ"]
        thisGod = config.get("rename", f"God{thisGodID}", fallback=None)
        # If god id not defined (eg future DLC), go into the xmb data and get it
        if thisGod is None:
            # Delay parsing xmbs if not required. It's slow and currently will parse all packed XMBs and not just major gods
            if xmbs is None:
                xmbs = parseXMB(filepath, hierarchy)
            try:
                civElem = xmbs["civs"].findall("civ")[thisGodID-1]
                thisGod = civElem.find("name").text
            except Exception:
                thisGod = f"Unk{thisGodID}"
                log(f"Failed to get name for god id {thisGodID} from packed game data, using '{thisGod}' instead")
        playerGodNames[playerIndex] = thisGod
        thisPlayerString = playerTemplate.replace("{PLAYER}", thisName).replace("{GOD}", thisGod)
        if thisTeam not in playersByTeam:
            playersByTeam[thisTeam] = []
        playersByTeam[thisTeam].append(thisPlayerString)
        
    
    # The profile keys derived metadata doesn't contain final team IDs - randoms will show as -1
    if -1 in playersByTeam:
        playersByTeam = {}
        # This place in the letter hierarchy happens to have them
        playerTreeData = hierarchy.find(["J1", "PL", "BP", "P1"])
        if len(playerTreeData) < 2:
            raise ValueError(f"Not enough player tree data, only found {len(playerTreeData)} items")
        playerNumber = 0
        for dataContainer in playerTreeData:
            # This may have some empty sections in, for some reason
            if len(dataContainer.data) < 5:
                continue
            # We do not care about mother nature
            if playerNumber > 0:
                # int32: player number
                # byte: 0?
                # String: the name once
                # bytes[9]: nulls
                # String: the name a second time
                # int32: team id
                stream = io.BytesIO(dataContainer.data)
                readPlayerNumber = readInt32(stream)
                stream.read(1)
                if readPlayerNumber != playerNumber:
                    raise ValueError(f"Binary player data mismatch: expected player number {playerNumber}, found {readPlayerNumber} instead")
                nameOne = readUtf16(stream)
                stream.read(9)
                nameTwo = readUtf16(stream)
                if nameOne != nameTwo:
                    raise ValueError(f"Binary player data mismatch: packed player names for p{playerNumber} did not match")
                thisTeam = readInt32(stream)
                if thisTeam not in playersByTeam:
                    playersByTeam[thisTeam] = []
                thisPlayerString = playerTemplate.replace("{PLAYER}", nameOne).replace("{GOD}", playerGodNames[playerNumber])
                playersByTeam[thisTeam].append(thisPlayerString)
                
            playerNumber += 1
    teamStrings = []
    for teamID, teamPlayerStrings in playersByTeam.items():
        teamStrings.append(" ".join(teamPlayerStrings))
    playerString = " vs ".join(teamStrings)
    
    name = nameTemplate.replace("{PLAYERS}", playerString)
    name = name.replace("{MAP}", metadata["gamemapname"].title())
    # Check for a timestamp in the filename already - eg Record Game 2024-09-21 04-34-17 giza Poseidon-Isis.mythrec
    existingTimestamp = re.match("Record Game (\\d{4})-(\\d{2})-(\\d{2})", os.path.split(filepath)[1])
    if existingTimestamp is not None:
        year, month, day = map(int, existingTimestamp.groups())
        timestamp = datetime.date(year, month, day)
    else:
        timestamp = datetime.date.fromtimestamp(os.path.getctime(filepath))
    name = name.replace("{TIMESTAMP}", timestamp.strftime("%Y-%m-%d"))
    head, tail = os.path.split(filepath)
    trailingCharacters = ""
    if config.getboolean("rename", "MarkRenamedRecs", fallback=True):
        trailingCharacters += "_"
    maxFilenameLength = int(config.get("rename", "MaxFilenameLength"))
    if len(name) > maxFilenameLength:
        name = name[:maxFilenameLength]
    for illegalchar in ILLEGAL_FILENAME_CHARACTERS:
        name = name.replace(illegalchar, ".")
    newfilepath = os.path.join(head, name) + trailingCharacters + ".mythrec"
    
    attempt = 2
    while os.path.isfile(newfilepath):
        newfilepath = os.path.join(head, name) + str(attempt) + trailingCharacters + ".mythrec"
        attempt += 1
    log(f"Renaming: {filepath} -> {newfilepath}")
    os.rename(filepath, newfilepath)
    for extra in (".json", ".decompressed"):
        if os.path.isfile(filepath + extra):
            log(f"Renaming: {filepath + extra} -> {newfilepath + extra}")
            os.rename(filepath + extra, newfilepath + extra)

def processFile(filepath: str):
    global config
    with open(filepath, "rb") as f:
        decompressed = decompressl33tZlib(f, RECORDED_GAME_MAX_DECOMPRESS_SIZE)
    
    if config.getboolean("development", "OutputDecompressed", fallback=False):
        decompressed.seek(0)
        with open(filepath + ".decompressed", "wb") as f:
            f.write(decompressed.read())
        decompressed.seek(0)
    hierarchy = tryParsingHierarchy(decompressed)
    metadata = parseMetadata(hierarchy)
    if config.getboolean("development", "OutputJson", fallback=False):
        with open(filepath + ".json", "w") as f:
            json.dump(metadata, f, indent=1)
    if config.getboolean("development", "OutputXmb", fallback=False):
        parseXMB(filepath, hierarchy, output=True)
    if config.getboolean("rename", "Rename", fallback=True):
        renameRec(filepath, metadata, hierarchy)

config = configparser.ConfigParser()

def shouldOperateOnFile(filepath: str) -> bool:
    global config
    if not os.path.isfile(filepath):
        return False
    if not filepath.endswith(".mythrec"):
        return False
    if filepath.endswith("_.mythrec") and config.getboolean("rename", "IgnoreRecsEndingWithUnderscore", fallback=True):
        return False
    return True

logfile = None

def log(str: str):
    global config, logfile
    if config.getboolean("development", "Log", fallback=True):
        if logfile is None:
            logfile = open(LOGFILE, "w")
        logfile.write(str + "\n")

def joinAndProcess(root, file):
    joinedPath = os.path.join(root, file)
    if shouldOperateOnFile(joinedPath):
        try:
            processFile(joinedPath)
        except Exception:
            log(f"FAILED to process {joinedPath}:")
            log(traceback.format_exc())
            return
        log(f"Processed {joinedPath} successfully")

def main():
    global config, logfile
    try:
        try:
            config.read("./recprocessor.ini")
        except FileNotFoundError:
            with open(LOGFILE, "w") as f:
                f.write("Could not find recprocessor.ini. Exiting.")
            return
        dirsToProcess = []
        index = 1
        while True:
            thisDir = config.get("recprocessor", f"ReplayFolder{index}", fallback="")
            if thisDir == "":
                break
            dirsToProcess.append(thisDir)
            index += 1

        for dirToWorkOn in dirsToProcess:
            if not os.path.isdir(dirToWorkOn):
                log(f"Target folder {dirToWorkOn} doesn't exist or isn't a folder, ignored")
                continue
            if config.getboolean("recprocessor", "RecursiveFolderCheck", fallback=False):
                for root, dirs, files in os.walk(dirToWorkOn):
                    for file in files:
                        joinAndProcess(root, file)
            else:
                for file in os.listdir(dirToWorkOn):
                    joinAndProcess(dirToWorkOn, file)
    except:
        log("FATAL ERROR")
        log(traceback.format_exc())
        
    log("Finished processing.")

    if logfile is not None:
        logfile.close()
		

if __name__ == "__main__":
    main()