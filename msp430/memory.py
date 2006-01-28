# $Id: memory.py,v 1.4 2006/01/28 15:35:42 cliechti Exp $
import sys
import elf

DEBUG = 0

class FileFormatError(IOError):
    """file is not in the expected format"""


class Segment:
    """store a string with memory contents along with its startaddress"""
    def __init__(self, startaddress = 0, data=None):
        if data is None:
            self.data = ''
        else:
            self.data = data
        self.startaddress = startaddress

    def __getitem__(self, index):
        return self.data[index]

    def __len__(self):
        return len(self.data)

    def __repr__(self):
        return "Segment(startaddress = 0x%04x, data=%r)" % (self.startaddress, self.data)

class Memory:
    """represent memory contents. with functions to load files"""
    def __init__(self, filename=None):
        self.segments = []
        if filename:
            self.filename = filename
            self.loadFile(filename)

    def append(self, seg):
        self.segments.append(seg)

    def __getitem__(self, index):
        return self.segments[index]

    def __len__(self):
        return len(self.segments)

    # - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -

    def loadIHex(self, file):
        """load data from a (opened) file in Intel-HEX format"""
        segmentdata = []
        currentAddr = 0
        startAddr   = 0
        lines = file.readlines()
        for l in lines:
            if not l.strip(): continue  #skip empty lines
            if l[0] != ':': raise FileFormatError("line not valid intel hex data: '%s...'" % l[0:10])
            l = l.strip()               #fix CR-LF issues...
            length  = int(l[1:3],16)
            address = int(l[3:7],16)
            type    = int(l[7:9],16)
            check   = int(l[-2:],16)
            if type == 0x00:
                if currentAddr != address:
                    if segmentdata:
                        self.segments.append( Segment(startAddr, ''.join(segmentdata)) )
                    startAddr = currentAddr = address
                    segmentdata = []
                for i in range(length):
                    segmentdata.append( chr(int(l[9+2*i:11+2*i],16)) )
                currentAddr = length + currentAddr
            elif type in (0x01, 0x02, 0x03, 0x04, 0x05):
                pass
            else:
                sys.stderr.write("Ignored unknown field (type 0x%02x) in ihex file.\n" % type)
        if segmentdata:
            self.segments.append( Segment(startAddr, ''.join(segmentdata)) )

    def loadTIText(self, file):
        """load data from a (opened) file in TI-Text format"""
        startAddr   = 0
        segmentdata = []
        #Convert data for MSP430, TXT-File is parsed line by line
        for line in file:       #Read one line
            if not line: break #EOF
            l = line.strip()
            if l[0] == 'q': break
            elif l[0] == '@':        #if @ => new address => send frame and set new addr.
                #create a new segment
                if segmentdata:
                    self.segments.append( Segment(startAddr, ''.join(segmentdata)) )
                startAddr = int(l[1:],16)
                segmentdata = []
            else:
                for i in l.split():
                    try:
                        segmentdata.append(chr(int(i,16)))
                    except ValueError, e:
                        raise FileFormatError('File is no valid TI-Text (%s)' % e)
        if segmentdata:
            self.segments.append( Segment(startAddr, ''.join(segmentdata)) )

    def loadELF(self, file):
        """load data from a (opened) file in ELF object format.
        File must be seekable"""
        obj = elf.ELFObject()
        obj.fromFile(file)
        if obj.e_type != elf.ELFObject.ET_EXEC:
            raise Exception("No executable")
        for section in obj.getSections():
            if DEBUG:
                sys.stderr.write("ELF section %s at 0x%04x %d bytes\n" % (section.name, section.lma, len(section.data)))
            if len(section.data):
                self.segments.append( Segment(section.lma, section.data) )
        
    def loadFile(self, filename):
        """fill memory with the contents of a file. file type is determined from extension"""
        #first check extension
        try:
            if filename[-4:].lower() == '.txt':
                self.loadTIText(open(filename, "rb"))
                return
            elif filename[-4:].lower() in ('.a43', '.hex'):
                self.loadIHex(open(filename, "rb"))
                return
        except FileFormatError:
            pass #do contents based detection below
        #then do a contents based detection
        try:
            self.loadELF(open(filename, "rb"))
        except elf.ELFException:
            try:
                self.loadIHex(open(filename, "rb"))
            except FileFormatError:
                try:
                    self.loadTIText(open(filename, "rb"))
                except FileFormatError:
                    raise FileFormatError('file could not be loaded (not ELF, IHex, or Ti-Text)')

    # - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
    def saveIHex(self, filelike):
        """write a string containing intel hex to given file object"""
        noeof=0
        for seg in self.segments:
            address = seg.startaddress
            data    = seg.data
            start = 0
            while start<len(data):
                end = start + 16
                if end > len(data): end = len(data)
                filelike.write(self._ihexline(address, data[start:end]))
                start += 16
                address += 16
        filelike.write(self._ihexline(0, [], end=1))   #append no data but an end line
    
    def _ihexline(self, address, buffer, end=0):
        """internal use: generate a line with intel hex encoded data"""
        out = []
        if end:
            type = 1
        else:
            type = 0
        out.append( ':%02X%04X%02X' % (len(buffer),address&0xffff,type) )
        sum = len(buffer) + ((address>>8)&255) + (address&255) + (type&255)
        for b in [ord(x) for x in buffer]:
            out.append('%02X' % (b&255) )
            sum += b&255
        out.append('%02X\r\n' %( (-sum)&255))
        return ''.join(out)
    
    def saveTIText(self, filelike):
        """output TI-Text to given file object"""
        for segment in self.segments:
            filelike.write("@%04x\n" % segment.startaddress)
            for i in range(0, len(segment.data), 16):
                filelike.write("%s\n" % " ".join(["%02x" % ord(x) for x in segment.data[i:i+16]]))
        filelike.write("q\n")
    # - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
    
    def getMemrange(self, fromadr, toadr):
        """get a range of bytes from the memory. unavailable values are filled with 0xff."""
        res = ''
        toadr = toadr + 1   #python indexes are excluding end, so include it
        while fromadr < toadr:
            for seg in self.segments:
                segend = seg.startaddress + len(seg.data)
                if seg.startaddress <= fromadr and fromadr < segend:
                    if toadr > segend:   #not all data in segment
                        catchlength = segend - fromadr
                    else:
                        catchlength = toadr - fromadr
                    res = res + seg.data[fromadr-seg.startaddress : fromadr-seg.startaddress+catchlength]
                    fromadr = fromadr + catchlength    #adjust start
                    if len(res) >= toadr-fromadr:
                        break   #return res
            else:   #undefined memory is filled with 0xff
                res = res + chr(255)
                fromadr = fromadr + 1 #adjust start
        return res

    def getMem(self, address, size):
        """get a range of bytes from the memory. a ValueError is raised if
           unavailable addresses are tried to read"""
        data = []
        for seg in self.segments:
            #~ print "0x%04x  " * 2 % (seg.startaddress, seg.startaddress + len(seg.data))
            if seg.startaddress <= address and seg.startaddress + len(seg.data) >= address:
                #segment contains data in the address range
                offset = address - seg.startaddress
                length = min(len(seg.data)-offset, size)
                data.append(seg.data[offset:offset+length])
                address += length
        value = ''.join(data)
        if len(value) != size:
            raise ValueError("could not collect the requested data")
        return value
    
    def setMem(self, address, contents):
        """write a range of bytes to the memory. a segment covering the address
           range to be written has to be existent. a ValueError is raised if not
           all data could be written (attention: a part of the data may have been
           written!)"""
        data = []
        for seg in self.segments:
            #~ print "0x%04x  " * 2 % (seg.startaddress, seg.startaddress + len(seg.data))
            if seg.startaddress <= address and seg.startaddress + len(seg.data) >= address:
                #segment contains data in the address range
                offset = address - seg.startaddress
                length = min(len(seg.data)-offset, len(contents))
                seg.data = seg.data[:offset] + contents[:length] + seg.data[offset+length:]
                contents = contents[length:]    #cut away what is used
                if not contents: break          #stop if done
                address += length
        raise ValueError("could not write all data")
