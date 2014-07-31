import subprocess
import sys
import time
import os, os.path
import grp, pwd
from pwd import getpwnam
from string import Template

import libvirt

import logger
import tools
import plnode.bwlimit as bwlimit

STATES = {
    libvirt.VIR_DOMAIN_NOSTATE:  'no state',
    libvirt.VIR_DOMAIN_RUNNING:  'running',
    libvirt.VIR_DOMAIN_BLOCKED:  'blocked on resource',
    libvirt.VIR_DOMAIN_PAUSED:   'paused by user',
    libvirt.VIR_DOMAIN_SHUTDOWN: 'being shut down',
    libvirt.VIR_DOMAIN_SHUTOFF:  'shut off',
    libvirt.VIR_DOMAIN_CRASHED:  'crashed',
}

def get_interfaces_xml(rec):
    xml = """
<interface type='network'>
  <source network='default'/>
</interface>
"""
    logger.log('create_lxc.py: interface XML is: %s' % xml)

    return xml

def configure(name, rec):
    """Write <rec['keys']> to my authorized_keys file."""
    logger.verbose('create_lxc: configuring %s'%name)
    #new_keys = rec['keys']
    
    # get the unix account info
    gid = grp.getgrnam("slices")[2]
    pw_info = pwd.getpwnam(name)
    uid = pw_info[2]
    pw_dir = pw_info[5]

    # write out authorized_keys file and conditionally create
    # the .ssh subdir if need be.
    dot_ssh = os.path.join(pw_dir,'.ssh')
    if not os.path.isdir(dot_ssh):
        if not os.path.isdir(pw_dir):
            logger.verbose('create_lxc: WARNING: homedir %s does not exist for %s!'%(pw_dir,name))
            os.mkdir(pw_dir)
            os.chown(pw_dir, uid, gid)
        os.mkdir(dot_ssh)

    auth_keys = os.path.join(dot_ssh,'authorized_keys')

    for new_keys in rec['keys']:
	tools.write_file(auth_keys, lambda f: f.write(new_keys['key']))

    # set access permissions and ownership properly
    os.chmod(dot_ssh, 0700)
    os.chown(dot_ssh, uid, gid)
    os.chmod(auth_keys, 0600)
    os.chown(auth_keys, uid, gid)

    logger.log('create_lxc: %s: installed ssh keys' % name)

def create_lxc(name, rec=None):
        ''' Create dirs, copy fs image, creat_lxc '''
        logger.verbose ('sliver_lxc: %s create'%(name))
        conn = libvirt.open("lxc://")
       
	try: 
            p = conn.lookupByName(name)
            logger.log("create_lxc: there is already a running vm %s!"%(name))
            return
	except:
            logger.log("create a new sliver %s"%(name))
		#return

        # Get the type of image from vref myplc tags specified as:
        # pldistro = lxc
        # fcdistro = squeeze
        # arch x86_64

        arch = 'x86_64'
        #tags = rec['rspec']['tags']
        #if 'arch' in tags:
        #    arch = tags['arch']
        #    if arch == 'i386':
        #        arch = 'i686'

        vref = "lxc-f18-x86_64"
	#vref = rec['vref']
        #if vref is None:
        #    vref = "lxc-f14-x86_64"
        #    logger.log("sliver_libvirt: %s: WARNING - no vref attached, using hard-wired default %s" % (name,vref))

        refImgDir    = os.path.join('/vservers/.lvref', vref)
        containerDir = os.path.join('/vservers', name)

        # check the template exists -- there's probably a better way..
        if not os.path.isdir(refImgDir):
            logger.log('creat_lxc: %s: ERROR Could not create sliver - reference image %s not found' % (name,vref))
            logger.log('creat_lxc: %s: ERROR Expected reference image in %s'%(name,refImgDir))
            return

        # Snapshot the reference image fs (assume the reference image is in its own
        # subvolume)
        command = ['btrfs', 'subvolume', 'snapshot', refImgDir, containerDir]
        if not logger.log_call(command, timeout=15*60):
            logger.log('creat_lxc: ERROR Could not create BTRFS snapshot at', containerDir)
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
        command = ['/usr/sbin/useradd', '-g', 'slices', '-s', '/usr/sbin/vsh', name, '-p', '*']
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
        template_filename_sliceimage = os.path.join('/vservers/.lvref','lxc_template.xml')
        if os.path.isfile (template_filename_sliceimage):
            logger.log("WARNING: using compat template %s"%template_filename_sliceimage)
            template_filename=template_filename_sliceimage
        else:
            logger.log("Cannot find XML template %s"%template_filename_sliceimage)
            return

        interfaces = get_interfaces_xml(rec)

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

	def debuginfo(dom):
        	''' Helper method to get a "nice" output of the info struct for debug'''
        	[state, maxmem, mem, ncpu, cputime] = dom.info()
	        return '%s is %s, maxmem = %s, mem = %s, ncpu = %s, cputime = %s' % (dom.name(), STATES.get(state, state), maxmem, mem, ncpu, cputime)

        logger.verbose('create_lxc: %s -> %s'%(name, debuginfo(dom)))

	# the sliver has been created
	# then configure the sliver, write keys to authorized_keys file
	configure(name, rec)

	# finally, start the sliver
	dom.create()
	logger.verbose('create_lxc:%s start'%(name))

	# After the VM is started... we can play with the virtual interface
        # Create the ebtables rule to mark the packets going out from the virtual
        # interface to the actual device so the filter canmatch against the mark
        bwlimit.ebtables("-A INPUT -i veth%d -j mark --set-mark %d" % \
            (xid, xid))
