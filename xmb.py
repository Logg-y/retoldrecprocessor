# Derived from reverse engineering resourcemanager's xmb parser
# In .bar files most seem to be "alz4" compressed as well, which ILSpy can help with as well and looks pretty simple

import struct
import typing
import xml.etree.ElementTree as ET

class XMBError(Exception):
    pass

def readUint32(stream: typing.BinaryIO) -> int:
    return struct.unpack("<i", stream.read(4))[0]

def readUtf16(stream: typing.BinaryIO) -> str:
    length = readUint32(stream)
    s = stream.read(length*2).decode("utf-16-le")
    return s

def parseXMBStream(stream: typing.BinaryIO) -> ET.Element:
    header = stream.read(2)
    if header != b"X1":
        raise XMBError(f"Bad X1 header at {stream.tell()}: got {header.decode(errors='replace')}")
    dataLength = readUint32(stream)
    unk1 = stream.read(2)
    if unk1 != b"XR":
        raise XMBError(f"Bad XR header at {stream.tell()}: got {unk1.decode(errors='replace')}")
    unk2 = readUint32(stream)
    if unk2 != 4:
        raise XMBError(f"Bad unk2 at {stream.tell()}: got {unk2}, expected 4")
    version = readUint32(stream)
    if version != 8:
        raise XMBError(f"Bad version at {stream.tell()}: got {version}, expected 8")
    numElements = readUint32(stream)
    elements: typing.List[str] = []
    for x in range(0, numElements):
        elements.append(readUtf16(stream))
    numAttributes = readUint32(stream)
    attributes: typing.List[str] = []
    for x in range(0, numAttributes):
        attributes.append(readUtf16(stream))
    root = parseNodeRecursive(stream, None, elements, attributes)
    tree = ET.ElementTree(root)
    ET.indent(tree)
    return tree

def parseNodeRecursive(stream: typing.BinaryIO, parent: typing.Union[None, ET.Element], elements: typing.List[str], attributes: typing.List[str]) -> ET.Element:
    header = stream.read(2)
    if header == b"XN":
        unk = stream.read(4)
        innerText = readUtf16(stream)
        nameID = readUint32(stream)
        name = elements[nameID]
        unk2 = stream.read(4)
        numAttribs = readUint32(stream)
        attribs: typing.Dict[str, str] = {}
        for x in range(0, numAttribs):
            attribID = readUint32(stream)
            attribName = attributes[attribID]
            attribValue = readUtf16(stream)
            attribs[attribName] = attribValue

        if parent is None:
            newparent = ET.Element(name, attribs)
        else:
            newparent = ET.SubElement(parent, name, attribs)
        newparent.text = innerText

        numChildren = readUint32(stream)
        for x in range(0, numChildren):
            parseNodeRecursive(stream, newparent, elements, attributes)
            
        return newparent
                
    else:
        raise XMBError(f"Bad XR header in parseNodeRecursive at {stream.tell()}: got {header.decode(errors='replace')}")
        
