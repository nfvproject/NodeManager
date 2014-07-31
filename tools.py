"""A few things that didn't seem to fit anywhere else."""

import os, os.path
import pwd
import tempfile
import fcntl
import errno
import threading
import subprocess
import shutil
import sys

import logger

PID_FILE = '/var/run/nodemanager.pid'

####################
def get_default_if():
    interface = get_if_from_hwaddr(get_hwaddr_from_plnode())
    if not interface: interface = "eth0"
    return interface

def get_hwaddr_from_plnode():
    try:
        for line in open("/usr/boot/plnode.txt", 'r').readlines():
            if line.startswith("NET_DEVICE"):
                return line.split("=")[1].strip().strip('"')
    except:
        pass
    return None

def get_if_from_hwaddr(hwaddr):
    import sioc
    devs = sioc.gifconf()
    for dev in devs:
        dev_hwaddr = sioc.gifhwaddr(dev)
        if dev_hwaddr == hwaddr: return dev
    return None

####################
# daemonizing
def as_daemon_thread(run):
    """Call function <run> with no arguments in its own thread."""
    thr = threading.Thread(target=run)
    thr.setDaemon(True)
    thr.start()

def close_nonstandard_fds():
    """Close all open file descriptors other than 0, 1, and 2."""
    _SC_OPEN_MAX = 4
    for fd in range(3, os.sysconf(_SC_OPEN_MAX)):
        try: os.close(fd)
        except OSError: pass  # most likely an fd that isn't open

# after http://www.erlenstar.demon.co.uk/unix/faq_2.html
def daemon():
    """Daemonize the current process."""
    if os.fork() != 0: os._exit(0)
    os.setsid()
    if os.fork() != 0: os._exit(0)
    os.chdir('/')
    os.umask(0022)
    devnull = os.open(os.devnull, os.O_RDWR)
    os.dup2(devnull, 0)
    # xxx fixme - this is just to make sure that nothing gets stupidly lost - should use devnull
    crashlog = os.open('/var/log/nodemanager.daemon', os.O_RDWR | os.O_APPEND | os.O_CREAT, 0644)
    os.dup2(crashlog, 1)
    os.dup2(crashlog, 2)

def fork_as(su, function, *args):
    """fork(), cd / to avoid keeping unused directories open, close all nonstandard file descriptors (to avoid capturing open sockets), fork() again (to avoid zombies) and call <function> with arguments <args> in the grandchild process.  If <su> is not None, set our group and user ids appropriately in the child process."""
    child_pid = os.fork()
    if child_pid == 0:
        try:
            os.chdir('/')
            close_nonstandard_fds()
            if su:
                pw_ent = pwd.getpwnam(su)
                os.setegid(pw_ent[3])
                os.seteuid(pw_ent[2])
            child_pid = os.fork()
            if child_pid == 0: function(*args)
        except:
            os.seteuid(os.getuid())  # undo su so we can write the log file
            os.setegid(os.getgid())
            logger.log_exc("tools: fork_as")
        os._exit(0)
    else: os.waitpid(child_pid, 0)

####################
# manage files
def pid_file():
    """We use a pid file to ensure that only one copy of NM is running at a given time.
If successful, this function will write a pid file containing the pid of the current process.
The return value is the pid of the other running process, or None otherwise."""
    other_pid = None
    if os.access(PID_FILE, os.F_OK):  # check for a pid file
        handle = open(PID_FILE)  # pid file exists, read it
        other_pid = int(handle.read())
        handle.close()
        # check for a process with that pid by sending signal 0
        try: os.kill(other_pid, 0)
        except OSError, e:
            if e.errno == errno.ESRCH: other_pid = None  # doesn't exist
            else: raise  # who knows
    if other_pid == None:
        # write a new pid file
        write_file(PID_FILE, lambda f: f.write(str(os.getpid())))
    return other_pid

def write_file(filename, do_write, **kw_args):
    """Write file <filename> atomically by opening a temporary file, using <do_write> to write that file, and then renaming the temporary file."""
    shutil.move(write_temp_file(do_write, **kw_args), filename)

def write_temp_file(do_write, mode=None, uidgid=None):
    fd, temporary_filename = tempfile.mkstemp()
    if mode: os.chmod(temporary_filename, mode)
    if uidgid: os.chown(temporary_filename, *uidgid)
    f = os.fdopen(fd, 'w')
    try: do_write(f)
    finally: f.close()
    return temporary_filename

# replace a target file with a new contents - checks for changes
# can handle chmod if requested
# can also remove resulting file if contents are void, if requested
# performs atomically:
#    writes in a tmp file, which is then renamed (from sliverauth originally)
# returns True if a change occurred, or the file is deleted
def replace_file_with_string (target, new_contents, chmod=None, remove_if_empty=False):
    try:
        current=file(target).read()
    except:
        current=""
    if current==new_contents:
        # if turns out to be an empty string, and remove_if_empty is set,
        # then make sure to trash the file if it exists
        if remove_if_empty and not new_contents and os.path.isfile(target):
            logger.verbose("tools.replace_file_with_string: removing file %s"%target)
            try: os.unlink(target)
            finally: return True
        return False
    # overwrite target file: create a temp in the same directory
    path=os.path.dirname(target) or '.'
    fd, name = tempfile.mkstemp('','repl',path)
    os.write(fd,new_contents)
    os.close(fd)
    if os.path.exists(target):
        os.unlink(target)
    shutil.move(name,target)
    if chmod: os.chmod(target,chmod)
    return True


####################
# utilities functions to get (cached) information from the node

# get node_id from /etc/planetlab/node_id and cache it
_node_id=None
def node_id():
    global _node_id
    if _node_id is None:
        try:
            _node_id=int(file("/etc/planetlab/node_id").read())
        except:
            _node_id=""
    return _node_id

_root_context_arch=None
def root_context_arch():
    global _root_context_arch
    if not _root_context_arch:
        sp=subprocess.Popen(["uname","-i"],stdout=subprocess.PIPE)
        (_root_context_arch,_)=sp.communicate()
        _root_context_arch=_root_context_arch.strip()
    return _root_context_arch


####################
class NMLock:
    def __init__(self, file):
        logger.log("tools: Lock %s initialized." % file, 2)
        self.fd = os.open(file, os.O_RDWR|os.O_CREAT, 0600)
        flags = fcntl.fcntl(self.fd, fcntl.F_GETFD)
        flags |= fcntl.FD_CLOEXEC
        fcntl.fcntl(self.fd, fcntl.F_SETFD, flags)
    def __del__(self):
        os.close(self.fd)
    def acquire(self):
        logger.log("tools: Lock acquired.", 2)
        fcntl.lockf(self.fd, fcntl.LOCK_SH)
    def release(self):
        logger.log("tools: Lock released.", 2)
        fcntl.lockf(self.fd, fcntl.LOCK_UN)

####################
# Utilities for getting the IP address of a LXC/Openvswitch slice. Do this by
# running ifconfig inside of the slice's context.

def get_sliver_process(slice_name, process_cmdline):
    """ Utility function to find a process inside of an LXC sliver. Returns
        (cgroup_fn, pid). cgroup_fn is the filename of the cgroup file for
        the process, for example /proc/2592/cgroup. Pid is the process id of
        the process. If the process is not found then (None, None) is returned.
    """
    try:
        cmd = 'grep %s /proc/*/cgroup | grep freezer'%slice_name
        output = os.popen(cmd).readlines()
    except:
        # the slice couldn't be found
        logger.log("get_sliver_process: couldn't find slice %s" % slice_name)
        return (None, None)

    cgroup_fn = None
    pid = None
    for e in output:
        try:
            l = e.rstrip()
            path = l.split(':')[0]
            comp = l.rsplit(':')[-1]
            slice_name_check = comp.rsplit('/')[-1]

            if (slice_name_check == slice_name):
                slice_path = path
                pid = slice_path.split('/')[2]
                cmdline = open('/proc/%s/cmdline'%pid).read().rstrip('\n\x00')
                if (cmdline == process_cmdline):
                    cgroup_fn = slice_path
                    break
        except:
            break

    if (not cgroup_fn) or (not pid):
        logger.log("get_sliver_process: process %s not running in slice %s" % (process_cmdline, slice_name))
        return (None, None)

    return (cgroup_fn, pid)

def get_sliver_ifconfig(slice_name, device="eth0"):
    """ return the output of "ifconfig" run from inside the sliver.

        side effects: adds "/usr/sbin" to sys.path
    """

    # See if setns is installed. If it's not then we're probably not running
    # LXC.
    if not os.path.exists("/usr/sbin/setns.so"):
        return None

    # setns is part of lxcsu and is installed to /usr/sbin
    if not "/usr/sbin" in sys.path:
        sys.path.append("/usr/sbin")
    import setns

    (cgroup_fn, pid) = get_sliver_process(slice_name, "/sbin/init")
    if (not cgroup_fn) or (not pid):
        return None

    path = '/proc/%s/ns/net'%pid

    result = None
    try:
        setns.chcontext(path)

        args = ["/sbin/ifconfig", device]
        sub = subprocess.Popen(args, stderr = subprocess.PIPE, stdout = subprocess.PIPE)
        sub.wait()

        if (sub.returncode != 0):
            logger.log("get_slice_ifconfig: error in ifconfig: %s" % sub.stderr.read())

        result = sub.stdout.read()
    finally:
        setns.chcontext("/proc/1/ns/net")

    return result

def get_sliver_ip(slice_name):
    ifconfig = get_sliver_ifconfig(slice_name)
    if not ifconfig:
        return None

    for line in ifconfig.split("\n"):
        if "inet addr:" in line:
            # example: '          inet addr:192.168.122.189  Bcast:192.168.122.255  Mask:255.255.255.0'
            parts = line.strip().split()
            if len(parts)>=2 and parts[1].startswith("addr:"):
                return parts[1].split(":")[1]

    return None

### this returns the kind of virtualization on the node
# either 'vs' or 'lxc'
# also caches it in /etc/planetlab/virt for next calls
# could be promoted to core nm if need be
virt_stamp="/etc/planetlab/virt"
def get_node_virt ():
    try:
        return file(virt_stamp).read().strip()
    except:
        pass
    logger.log("Computing virt..")
    try: 
        if subprocess.call ([ 'vserver', '--help' ]) ==0: virt='vs'
        else:                                             virt='lxc'      
    except:
        virt='lxc'
    with file(virt_stamp,"w") as f:
        f.write(virt)
    return virt

# how to run a command in a slice
# now this is a painful matter
# the problem is with capsh that forces a bash command to be injected in its exec'ed command
# so because lxcsu uses capsh, you cannot exec anything else than bash
# bottom line is, what actually needs to be called is
# vs:  vserver exec slicename command and its arguments
# lxc: lxcsu slicename "command and its arguments"
# which, OK, is no big deal as long as the command is simple enough, 
# but do not stretch it with arguments that have spaces or need quoting as that will become a nightmare
def command_in_slice (slicename, argv):
    virt=get_node_virt()
    if virt=='vs':
        return [ 'vserver', slicename, 'exec', ] + argv
    elif virt=='lxc':
        # wrap up argv in a single string for -c
        return [ 'lxcsu', slicename, ] + [ " ".join(argv) ]
    logger.log("command_in_slice: WARNING: could not find a valid virt")
    return argv

