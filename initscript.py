# Restarting nm (via systemctl):  Warning: Unit file of created job changed on disk, 'systemctl --system daemon-reload' recommended.

import os, os.path
import tools

import logger

class Initscript:

    def __init__ (self, name):
        self.name=name
        self.initscript = ''

    def configure (self, rec):
#        logger.log("Initscript.configure")
        new_initscript = rec['initscript']
        if new_initscript != self.initscript:
            self.initscript = new_initscript
            # not used anymore, we always check against the installed script
            #self.initscriptchanged = True
            self.refresh_slice_vinit()

    # unconditionnally install and enable the generic vinit script
    # mimicking chkconfig for enabling the generic vinit script
    # this is hardwired for runlevel 3
    def install_and_enable_vinit (self):
        vinit_source="/usr/share/NodeManager/sliver-initscripts/vinit"
        vinit_script="/vservers/%s/etc/rc.d/init.d/vinit"%self.name
        rc3_link="/vservers/%s/etc/rc.d/rc3.d/S99vinit"%self.name
        rc3_target="../init.d/vinit"
        # install in sliver
        code=file(vinit_source).read()
        if tools.replace_file_with_string(vinit_script,code,chmod=0755):
            logger.log("vsliver_vs: %s: installed generic vinit rc script"%self.name)
        # create symlink for runlevel 3
        if not os.path.islink(rc3_link):
            try:
                logger.log("vsliver_vs: %s: creating runlevel3 symlink %s"%(self.name,rc3_link))
                os.symlink(rc3_target,rc3_link)
            except:
                logger.log_exc("vsliver_vs: %s: failed to create runlevel3 symlink %s"%rc3_link)

    # install or remove the slice inistscript, as instructed by the initscript tag
    def refresh_slice_vinit(self):
        code=self.initscript
        sliver_initscript="/vservers/%s/etc/rc.d/init.d/vinit.slice"%self.name
        if tools.replace_file_with_string(sliver_initscript,code,remove_if_empty=True,chmod=0755):
            if code:
                logger.log("vsliver_vs: %s: Installed new initscript in %s"%(self.name,sliver_initscript))
                if self.is_running():
                    # Only need to rerun the initscript if the vserver is
                    # already running. If the vserver isn't running, then the
                    # initscript will automatically be started by
                    # /etc/rc.d/vinit when the vserver is started.
                    self.rerun_slice_vinit()
            else:
                logger.log("vsliver_vs: %s: Removed obsolete initscript %s"%(self.name,sliver_initscript))

