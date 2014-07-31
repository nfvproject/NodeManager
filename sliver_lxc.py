#

"""LXC slivers"""

import subprocess
import sys
import time
import os, os.path
import grp
from pwd import getpwnam
from string import Template

import libvirt

import logger
import plnode.bwlimit as bwlimit
from initscript import Initscript
from account import Account
from sliver_libvirt import Sliver_Libvirt

class Sliver_LXC(Sliver_Libvirt, Initscript):
    """This class wraps LXC commands"""

    SHELL = '/usr/sbin/vsh'
    TYPE = 'sliver.LXC'
    # Need to add a tag at myplc to actually use this account
    # type = 'sliver.LXC'

    REF_IMG_BASE_DIR = '/vservers/.lvref'
    CON_BASE_DIR     = '/vservers'

    def __init__ (self, rec):
        name=rec['name']
        Sliver_Libvirt.__init__ (self,rec)
        Initscript.__init__ (self,name)

    def configure (self, rec):
        Sliver_Libvirt.configure (self,rec)

        # in case we update nodemanager..
        self.install_and_enable_vinit()
        # do the configure part from Initscript
        Initscript.configure(self,rec)

    def start(self, delay=0):
        if 'enabled' in self.rspec and self.rspec['enabled'] <= 0:
            logger.log('sliver_lxc: not starting %s, is not enabled'%self.name)
            return
        # the generic /etc/init.d/vinit script is permanently refreshed, and enabled
        self.install_and_enable_vinit()
        # expose .ssh for omf_friendly slivers
        if 'tags' in self.rspec and 'omf_control' in self.rspec['tags']:
            Account.mount_ssh_dir(self.name)
        Sliver_Libvirt.start (self, delay)
        # if a change has occured in the slice initscript, reflect this in /etc/init.d/vinit.slice
        self.refresh_slice_vinit()

    def rerun_slice_vinit (self):
        """This is called whenever the initscript code changes"""
        # xxx - todo - not sure exactly how to:
        # (.) invoke something in the guest
        # (.) which options of systemctl should be used to trigger a restart
        # should not prevent the first run from going fine hopefully
        logger.log("WARNING: sliver_lxc.rerun_slice_vinit not implemented yet")

    @staticmethod
    def create(name, rec=None):
        ''' Create dirs, copy fs image, lxc_create '''
        logger.verbose ('sliver_lxc: %s create'%(name))
        conn = Sliver_Libvirt.getConnection(Sliver_LXC.TYPE)

        # Get the type of image from vref myplc tags specified as:
        # pldistro = lxc
        # fcdistro = squeeze
        # arch x86_64

        arch = 'x86_64'
        tags = rec['rspec']['tags']
        if 'arch' in tags:
            arch = tags['arch']
            if arch == 'i386':
                arch = 'i686'

        vref = rec['vref']
        if vref is None:
            vref = "lxc-f14-x86_64"
            logger.log("sliver_libvirt: %s: WARNING - no vref attached, using hard-wired default %s" % (name,vref))

        refImgDir    = os.path.join(Sliver_LXC.REF_IMG_BASE_DIR, vref)
        containerDir = os.path.join(Sliver_LXC.CON_BASE_DIR, name)

        # check the template exists -- there's probably a better way..
        if not os.path.isdir(refImgDir):
            logger.log('sliver_lxc: %s: ERROR Could not create sliver - reference image %s not found' % (name,vref))
            logger.log('sliver_lxc: %s: ERROR Expected reference image in %s'%(name,refImgDir))
            return

        # Snapshot the reference image fs (assume the reference image is in its own
        # subvolume)
        command = ['btrfs', 'subvolume', 'snapshot', refImgDir, containerDir]
        if not logger.log_call(command, timeout=15*60):
            logger.log('sliver_lxc: ERROR Could not create BTRFS snapshot at', containerDir)
            return
        command = ['chmod', '755', containerDir]
        logger.log_call(command, timeout=15*60)

        # TODO: set quotas...

        # Set hostname. A valid hostname cannot have '_'
        #with open(os.path.join(containerDir, 'etc/hostname'), 'w') as f:
        #    print >>f, name.replace('_', '-')

        # Add slices group if not already present
        try:
            group = grp.getgrnam('slices')
        except:
            command = ['/usr/sbin/groupadd', 'slices']
            logger.log_call(command, timeout=15*60)

        # Add unix account (TYPE is specified in the subclass)
        command = ['/usr/sbin/useradd', '-g', 'slices', '-s', Sliver_LXC.SHELL, name, '-p', '*']
        logger.log_call(command, timeout=15*60)
        command = ['mkdir', '/home/%s/.ssh'%name]
        logger.log_call(command, timeout=15*60)

        # Create PK pair keys to connect from the host to the guest without
        # password... maybe remove the need for authentication inside the
        # guest?
        command = ['su', '-s', '/bin/bash', '-c', 'ssh-keygen -t rsa -N "" -f /home/%s/.ssh/id_rsa'%(name)]
        logger.log_call(command, timeout=60)

        command = ['chown', '-R', '%s.slices'%name, '/home/%s/.ssh'%name]
        logger.log_call(command, timeout=30)

        command = ['mkdir', '%s/root/.ssh'%containerDir]
        logger.log_call(command, timeout=10)

        command = ['cp', '/home/%s/.ssh/id_rsa.pub'%name, '%s/root/.ssh/authorized_keys'%containerDir]
        logger.log_call(command, timeout=30)

        logger.log("creating /etc/slicename file in %s" % os.path.join(containerDir,'etc/slicename'))
        try:
            file(os.path.join(containerDir,'etc/slicename'), 'w').write(name)
        except:
            logger.log_exc("exception while creating /etc/slicename")

        try:
            file(os.path.join(containerDir,'etc/slicefamily'), 'w').write(vref)
        except:
            logger.log_exc("exception while creating /etc/slicefamily")

        uid = None
        try:
            uid = getpwnam(name).pw_uid
        except KeyError:
            # keyerror will happen if user id was not created successfully
            logger.log_exc("exception while getting user id")

        if uid is not None:
            logger.log("uid is %d" % uid)
            command = ['mkdir', '%s/home/%s' % (containerDir, name)]
            logger.log_call(command, timeout=10)
            command = ['chown', name, '%s/home/%s' % (containerDir, name)]
            logger.log_call(command, timeout=10)
            etcpasswd = os.path.join(containerDir, 'etc/passwd')
            etcgroup = os.path.join(containerDir, 'etc/group')
            if os.path.exists(etcpasswd):
                # create all accounts with gid=1001 - i.e. 'slices' like it is in the root context
                slices_gid=1001
                logger.log("adding user %(name)s id %(uid)d gid %(slices_gid)d to %(etcpasswd)s" % (locals()))
                try:
                    file(etcpasswd,'a').write("%(name)s:x:%(uid)d:%(slices_gid)d::/home/%(name)s:/bin/bash\n" % locals())
                except:
                    logger.log_exc("exception while updating %s"%etcpasswd)
                logger.log("adding group slices with gid %(slices_gid)d to %(etcgroup)s"%locals())
                try:
                    file(etcgroup,'a').write("slices:x:%(slices_gid)d\n"%locals())
                except:
                    logger.log_exc("exception while updating %s"%etcgroup)
            sudoers = os.path.join(containerDir, 'etc/sudoers')
            if os.path.exists(sudoers):
                try:
                    file(sudoers,'a').write("%s ALL=(ALL) NOPASSWD: ALL\n" % name)
                except:
                    logger.log_exc("exception while updating /etc/sudoers")

        # customizations for the user environment - root or slice uid
        # we save the whole business in /etc/planetlab.profile 
        # and source this file for both root and the slice uid's .profile
        # prompt for slice owner, + LD_PRELOAD for transparently wrap bind
        pl_profile=os.path.join(containerDir,"etc/planetlab.profile")
        ld_preload_text="""# by default, we define this setting so that calls to bind(2),
# when invoked on 0.0.0.0, get transparently redirected to the public interface of this node
# see https://svn.planet-lab.org/wiki/LxcPortForwarding"""
        usrmove_path_text="""# VM's before Features/UsrMove need /bin and /sbin in their PATH"""
        usrmove_path_code="""
pathmunge () {
        if ! echo $PATH | /bin/egrep -q "(^|:)$1($|:)" ; then
           if [ "$2" = "after" ] ; then
              PATH=$PATH:$1
           else
              PATH=$1:$PATH
           fi
        fi
}
pathmunge /bin after
pathmunge /sbin after
unset pathmunge
"""
        with open(pl_profile,'w') as f:
            f.write("export PS1='%s@\H \$ '\n"%(name))
            f.write("%s\n"%ld_preload_text)
            f.write("export LD_PRELOAD=/etc/planetlab/lib/bind_public.so\n")
            f.write("%s\n"%usrmove_path_text)
            f.write("%s\n"%usrmove_path_code)

        # make sure this file is sourced from both root's and slice's .profile
        enforced_line = "[ -f /etc/planetlab.profile ] && source /etc/planetlab.profile\n"
        for path in [ 'root/.profile', 'home/%s/.profile'%name ]:
            from_root=os.path.join(containerDir,path)
            # if dir is not yet existing let's forget it for now
            if not os.path.isdir(os.path.dirname(from_root)): continue
            found=False
            try: 
                contents=file(from_root).readlines()
                for content in contents:
                    if content==enforced_line: found=True
            except IOError: pass
            if not found:
                with open(from_root,"a") as user_profile:
                    user_profile.write(enforced_line)
                # in case we create the slice's .profile when writing
                if from_root.find("/home")>=0:
                    command=['chown','%s:slices'%name,from_root]
                    logger.log_call(command,timeout=5)

        # Lookup for xid and create template after the user is created so we
        # can get the correct xid based on the name of the slice
        xid = bwlimit.get_xid(name)

        # Template for libvirt sliver configuration
        template_filename_sliceimage = os.path.join(Sliver_LXC.REF_IMG_BASE_DIR,'lxc_template.xml')
        if os.path.isfile (template_filename_sliceimage):
            logger.log("WARNING: using compat template %s"%template_filename_sliceimage)
            template_filename=template_filename_sliceimage
        else:
            logger.log("Cannot find XML template %s"%template_filename_sliceimage)
            return

        interfaces = Sliver_Libvirt.get_interfaces_xml(rec)

        try:
            with open(template_filename) as f:
                template = Template(f.read())
                xml  = template.substitute(name=name, xid=xid, interfaces=interfaces, arch=arch)
        except IOError:
            logger.log('Failed to parse or use XML template file %s'%template_filename)
            return

        # Lookup for the sliver before actually
        # defining it, just in case it was already defined.
        try:
            dom = conn.lookupByName(name)
        except:
            dom = conn.defineXML(xml)
        logger.verbose('lxc_create: %s -> %s'%(name, Sliver_Libvirt.debuginfo(dom)))


    @staticmethod
    def destroy(name):
        # umount .ssh directory - only if mounted
        Account.umount_ssh_dir(name)
        logger.verbose ('sliver_lxc: %s destroy'%(name))
        conn = Sliver_Libvirt.getConnection(Sliver_LXC.TYPE)

        containerDir = Sliver_LXC.CON_BASE_DIR + '/%s'%(name)

        try:
            # Destroy libvirt domain
            dom = conn.lookupByName(name)
        except:
            logger.verbose('sliver_lxc: Domain %s does not exist!' % name)

        try:
            dom.destroy()
        except:
            logger.verbose('sliver_lxc: Domain %s not running... continuing.' % name)

        try:
            dom.undefine()
        except:
            logger.verbose('sliver_lxc: Domain %s is not defined... continuing.' % name)

        # Remove user after destroy domain to force logout
        command = ['/usr/sbin/userdel', '-f', '-r', name]
        logger.log_call(command, timeout=15*60)

        if os.path.exists(os.path.join(containerDir,"vsys")):
            # Slivers with vsys running will fail the subvolume delete.
            # A more permanent solution may be to ensure that the vsys module
            # is called before the sliver is destroyed.
            logger.log("destroying vsys directory and restarting vsys")
            logger.log_call(["rm", "-fR", os.path.join(containerDir, "vsys")])
            logger.log_call(["/etc/init.d/vsys", "restart", ])

        # Remove rootfs of destroyed domain
        command = ['btrfs', 'subvolume', 'delete', containerDir]
        logger.log_call(command, timeout=60)

        if os.path.exists(containerDir):
           # oh no, it's still here...
           logger.log("WARNING: failed to destroy container %s" % containerDir)

        logger.verbose('sliver_libvirt: %s destroyed.'%name)

