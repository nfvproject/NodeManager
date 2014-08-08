
"""A very simple logger that tries to be concurrency-safe."""

import os, sys
import time
import traceback
import subprocess
import select
import pickle

LOG_FILE    = '/var/log/nodemanager'
LOG_SLIVERS = '/var/lib/nodemanager/getslivers.txt'
LOG_SLICEMAP = '/var/lib/nodemanager/getmap.txt'
LOG_DATABASE = '/var/lib/nodemanager/database.txt'
LOG_MAP = '/var/log/slice/map.txt'
LOG_ROUTER = '/var/log/slice/router.txt'
LOG_PATH = '/var/log/slice/'

# basically define 3 levels
LOG_NONE=0
LOG_NODE=1
LOG_VERBOSE=2

# default is to log a reasonable amount of stuff for when running on operational nodes
LOG_LEVEL=LOG_NODE

def set_level(level):
    global LOG_LEVEL
    try:
        assert level in [LOG_NONE,LOG_NODE,LOG_VERBOSE]
        LOG_LEVEL=level
    except:
        logger.log("Failed to set LOG_LEVEL to %s"%level)

def verbose(msg):
    log('(v) '+msg,LOG_VERBOSE)

def logslice(msg,logfile):
    try:
        fd = os.open(logfile, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0600)
        if not msg.endswith('\n'): msg += '\n'
        os.write(fd, '%s' % (msg))
        os.close(fd)
    except OSError:
        sys.stderr.write(msg)
        sys.stderr.flush()    
def logmap(sliceid,vmid):
    mapfile = '/var/log/slice/map'
    msg = 't'
    msg +=str(sliceid)
    msg += '='
    msg += str(vmid)
    try:
        fd = os.open(mapfile, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0600)
        if not msg.endswith('\n'): msg += '\n'
        os.write(fd, '%s' % (msg))
        os.close(fd)
    except OSError:
        sys.stderr.write(msg)
        sys.stderr.flush() 
def log(msg,level=LOG_NODE):
    """Write <msg> to the log file if level >= current log level (default LOG_NODE)."""
    if (level > LOG_LEVEL):
        return
    try:
        fd = os.open(LOG_FILE, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0600)
        if not msg.endswith('\n'): msg += '\n'
        os.write(fd, '%s: %s' % (time.asctime(time.gmtime()), msg))
        os.close(fd)
    except OSError:
        sys.stderr.write(msg)
        sys.stderr.flush()

def log_exc(msg="",name=None):
    """Log traceback resulting from an exception."""
    printout=""
    if name: printout += "%s: "%name
    printout += "EXCEPTION caught <%s> \n %s" %(msg, traceback.format_exc())
    log(printout)

def log_trace(msg="",name=None):
    """Log current stack"""
    printout=""
    if name: printout += "%s: "%name
    printout += "LOGTRACE\n"
    for frame in traceback.format_stack():
        printout += "..."+frame
    log(printout)


########## snapshot data to a file
# for some reason the various modules are still triggered even when the
# data from PLC cannot be reached
# we show this message instead of the exception stack instead in this case
def log_missing_data (msg,key):
    log("%s: could not find the %s key in data (PLC connection down?) - IGNORED"%(msg,key))

def log_data_in_file (data, file, message="",level=LOG_NODE):
    if (level > LOG_LEVEL):
        return
    import pprint, time
    try:
        f=open(file,'w')
        now=time.strftime("Last update: %Y.%m.%d at %H:%M:%S %Z", time.localtime())
        f.write(now+'\n')
        if message: f.write('Message:'+message+'\n')
        pp=pprint.PrettyPrinter(stream=f,indent=2)
        pp.pprint(data)
        f.close()
        verbose("logger:.log_data_in_file Owerwrote %s"%file)
    except:
        log_exc('logger.log_data_in_file failed - file=%s - message=%r'%(file,message))
#wangyang
def log_map_in_file (data, file, message="",level=LOG_NODE):
    if (level > LOG_LEVEL):
        return
    import pprint, time
    try:
        f=open(file,'w')
        now=time.strftime("Last update: %Y.%m.%d at %H:%M:%S %Z", time.localtime())
        f.write(now+'\n')
        if message: f.write('Message:'+message+'\n')
        pp=pprint.PrettyPrinter(stream=f,indent=2)
        pp.pprint(data)
        f.close()
        verbose("logger:.log_data_in_file Owerwrote %s"%file)
    except:
        log_exc('logger.log_data_in_file failed - file=%s - message=%r'%(file,message))

def log_slivers (data):
    log_data_in_file (data, LOG_SLIVERS, "raw GetSlivers")
def log_slicemap (data):
    log_data_in_file (data, LOG_SLICEMAP, "raw GetMap")
def log_database (db):
    log_data_in_file (db, LOG_DATABASE, "raw database")
#wangyang
def log_map(data,info):
    log_map_in_file (data, LOG_MAP, info)

#wangyang
def log_router(data,filename,info):
    log_map_in_file (data, LOG_PATH+filename, info)
def log_db(data,filename):
    f=open(file,'w')
    pickle.dump(date, f)
    f.close()

    
#################### child processes
# avoid waiting until the process returns;
# that makes debugging of hanging children hard

class Buffer:
    def __init__ (self,message='log_call: '):
        self.buffer=''
        self.message=message

    def add (self,c):
        self.buffer += c
        if c=='\n': self.flush()

    def flush (self):
        if self.buffer:
            log (self.message + self.buffer)
            self.buffer=''

# time out in seconds - avoid hanging subprocesses - default is 5 minutes
default_timeout_minutes=5

# returns a bool that is True when everything goes fine and the retcod is 0
def log_call(command,timeout=default_timeout_minutes*60,poll=1):
    message=" ".join(command)
    log("log_call: running command %s" % message)
    verbose("log_call: timeout=%r s" % timeout)
    verbose("log_call: poll=%r s" % poll)
    trigger=time.time()+timeout
    result = False
    try:
        child = subprocess.Popen(command, bufsize=1,
                                 stdout=subprocess.PIPE, stderr=subprocess.STDOUT, close_fds=True)
        buffer = Buffer()
        while True:
            # see if anything can be read within the poll interval
            (r,w,x)=select.select([child.stdout],[],[],poll)
            if r: buffer.add(child.stdout.read(1))
            # is process over ?
            returncode=child.poll()
            # yes
            if returncode != None:
                buffer.flush()
                # child is done and return 0
                if returncode == 0:
                    log("log_call:end command (%s) completed" % message)
                    result=True
                    break
                # child has failed
                else:
                    log("log_call:end command (%s) returned with code %d" %(message,returncode))
                    break
            # no : still within timeout ?
            if time.time() >= trigger:
                buffer.flush()
                child.terminate()
                log("log_call:end terminating command (%s) - exceeded timeout %d s"%(message,timeout))
                break
    except: log_exc("failed to run command %s" % message)
    return result
