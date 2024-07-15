import typing
import struct
import io
import os
import json
import zlib
import configparser
import traceback
import datetime

RECORDED_GAME_MAX_DECOMPRESS_SIZE = 5*1024*1024
LOGFILE = "_recprocessor.log"

def decompressl33tZlib(stream: typing.BinaryIO, maxSize=0) -> typing.BinaryIO:
    "Decompress up to maxSize bytes of a l33t-zlib compressed file, returning a file-like object of decompressed data"
    header = stream.read(4)
    if header != b"l33t":
        raise ValueError(f"Bad l33t-zlib header: {header.decode(errors='replace')}")
    decompress = zlib.decompressobj()
    origDataLength = struct.unpack("<i", stream.read(4))[0]
    return io.BytesIO(decompress.decompress(stream.read(), maxSize))

def readInt32(stream: typing.BinaryIO) -> int:
    return struct.unpack("<i", stream.read(4))[0]

def readUtf16(stream: typing.BinaryIO) -> str:
    length = readInt32(stream)
    return stream.read(length*2).decode("utf16")

def parseMetadata(stream: typing.BinaryIO) -> typing.Dict[str, typing.Any]:
    "Process a decompressed recorded game file, returning a dict of the metadata array"
    # For now I feel like the safest assumption I can make for the file format is
    # that the keys are written in the same order
    # Vs AI games don't seem to have the same data in them!
    wholeContent = stream.read()
    startPos = wholeContent.find("gamename".encode("utf-16-le"))
    if startPos < 0:
        raise ValueError("Couldn't find metadata table in stream")
    # Go back 8 bytes.
    # 4 bytes: length of the gamename key
    # 4 bytes: number of keys in the array
    startPos -= 8
    stream.seek(startPos)
    numkeys = readInt32(stream)
    if numkeys > 5000:
        raise ValueError("Failed num keys sanity check. Something likely went wrong.")
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
            # Because it's at the end there's no way to tell what the actual length of this type is
            # If more keys come after it, things will probably go very wrong very quickly
            print(f"Found a keytype 3, which has unknown length - assumed zero")
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

def renameRec(filepath: str, metadata: typing.Dict[str, typing.Any]):
    global config
    nameTemplate = config.get("rename", "RenameFormat")
    playerTemplate = config.get("rename", "RenameFormatPlayer")
    playersByTeam = {}
    for playerIndex in range(1, metadata["gamenumplayers"]+1):
        thisTeam = metadata[f"gameplayer{playerIndex}teamid"]
        thisName = metadata[f"gameplayer{playerIndex}name"]
        thisGodID = metadata[f"gameplayer{playerIndex}civ"]
        thisGod = config.get("rename", f"God{thisGodID}", fallback=f"Unk{thisGodID}")
        thisPlayerString = playerTemplate.replace("{PLAYER}", thisName).replace("{GOD}", thisGod)
        if thisTeam not in playersByTeam:
            playersByTeam[thisTeam] = []
        playersByTeam[thisTeam].append(thisPlayerString)

    teamStrings = []
    for teamID, teamPlayerStrings in playersByTeam.items():
        teamStrings.append(" ".join(teamPlayerStrings))
    playerString = " vs ".join(teamStrings)

    name = nameTemplate.replace("{PLAYERS}", playerString)
    name = name.replace("{MAP}", metadata["gamemapname"].title())
    name = name.replace("{TIMESTAMP}", datetime.date.fromtimestamp(os.path.getctime(filepath)).strftime("%Y-%m-%d"))
    head, tail = os.path.split(filepath)
    trailingCharacters = ""
    if config.getboolean("rename", "MarkRenamedRecs", fallback=True):
        trailingCharacters += "_"
    newfilepath = os.path.join(head, name) + trailingCharacters + ".mythrec"
    attempt = 2
    while os.path.isfile(newfilepath):
        newfilepath = os.path.join(head, name) + str(attempt) + trailingCharacters + ".mythrec"
        attempt += 1
    log(f"Renaming: {filepath} -> {newfilepath}")
    os.rename(filepath, newfilepath)

def processFile(filepath: str):
    global config
    with open(filepath, "rb") as f:
        decompressed = decompressl33tZlib(f, RECORDED_GAME_MAX_DECOMPRESS_SIZE)
    if config.getboolean("development", "OutputDecompressed", fallback=False):
        with open(filepath + ".decompressed", "wb") as f:
            f.write(decompressed.read())
        decompressed.seek(0)
    metadata = parseMetadata(decompressed)
    if config.getboolean("development", "OutputJson", fallback=False):
        with open(filepath + ".json", "w") as f:
            json.dump(metadata, f, indent=1)
    if config.getboolean("rename", "Rename", fallback=True):
        renameRec(filepath, metadata)

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
        except:
            log(f"FAILED to process {joinedPath}:")
            log(traceback.format_exc())
            return
        log(f"Processed {joinedPath} successfully")

def main():
    global config, logfile
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

    if logfile is not None:
        logfile.close()


if __name__ == "__main__":
    main()