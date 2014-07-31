#
# NodeManager plugin - first step of handling omf_controlled slices
#

"""
Overwrites the 'resctl' tag of slivers controlled by OMF so slivermanager.py does the right thing
"""

import os, os.path
import glob
import subprocess

import tools
import logger

# we need this to run after sliverauth
priority = 150

def start():
    pass

### the new template for OMF v6
# hard-wire this for now
# once the variables are expanded, this is expected to go into
config_ple_template="""---
# we extract expires time here, even in a comment so that the
# trigger script gets called whenever this changes
# expires: _expires_

# these are not actual OMF parameters, they are only used by the trigger script
:hostname: _hostname_
:slicename: _slicename_

# OMF configuration
:uid: _slicename_%_hostname_
:uri: xmpp://_slicename_-_hostname_-<%= "#{Process.pid}" %>:_slicename_-_hostname_-<%= "#{Process.pid}" %>@_xmpp_server_
:environment: production
:debug: false
 
:auth:
  :root_cert_dir: /home/_slicename_/root_certs
  :entity_cert: /home/_slicename_/entity.crt
  :entity_key: /home/_slicename_/.ssh/id_rsa
"""

# the path where the config is expected from within the sliver
yaml_slice_path="/etc/omf_rc/config.yml"
# the path for the script that we call when a change occurs
# given that we're now responsible for fetching this one, I have to
# decide on an actual path - not jsut a name to search for in PATH
omf_rc_trigger_script="/usr/bin/plc_trigger_omf_rc"
omf_rc_trigger_log="/var/log/plc_trigger_omf_rc.log"

# hopefully temporary: when trigger script is missing, fetch it at the url here
omf_rc_trigger_url="http://git.mytestbed.net/?p=omf.git;a=blob_plain;f=omf_rc/bin/plc_trigger_omf_rc;hb=HEAD"
def fetch_trigger_script_if_missing (slicename):
    full_path="/vservers/%s/%s"%(slicename,omf_rc_trigger_script)
    if not os.path.isfile (full_path):
        retcod=subprocess.call (['curl','--silent','-o',full_path,omf_rc_trigger_url])
        if retcod!=0:
            logger.log("Could not fetch %s"%omf_rc_trigger_url)
        else:
            subprocess.call(['chmod','+x',full_path])
            logger.log("omf_resctl: fetched %s"%(full_path))
            logger.log("omf_resctl: from %s"%(omf_rc_trigger_url))

def GetSlivers(data, conf = None, plc = None):
    logger.log("omf_resctl.GetSlivers")
    if 'accounts' not in data:
        logger.log_missing_data("omf_resctl.GetSlivers",'accounts')
        return

    try:
        xmpp_server=data['xmpp']['server']
        if not xmpp_server: 
            # we have the key but no value, just as bad
            raise Exception
    except:
        # disabled feature - bailing out
        logger.log("omf_resctl: PLC_OMF config unsufficient (not enabled, or no server set), -- plugin exiting")
        return

    hostname = data['hostname']

    def is_omf_friendly (sliver):
        for chunk in sliver['attributes']:
            if chunk['tagname']=='omf_control': return True

    for sliver in data['slivers']:
        # skip non OMF-friendly slices
        if not is_omf_friendly (sliver): continue
        slicename=sliver['name']
        expires=str(sliver['expires'])
        yaml_template = config_ple_template
        yaml_contents = yaml_template\
            .replace('_xmpp_server_',xmpp_server)\
            .replace('_slicename_',slicename)\
            .replace('_hostname_',hostname)\
            .replace('_expires_',expires)
        yaml_full_path="/vservers/%s/%s"%(slicename,yaml_slice_path)
        yaml_full_dir=os.path.dirname(yaml_full_path)
        if not os.path.isdir(yaml_full_dir):
            try: os.makedirs(yaml_full_dir)
            except OSError: pass

        config_changes=tools.replace_file_with_string(yaml_full_path,yaml_contents)
        logger.log("yaml_contents length=%d, config_changes=%r"%(len(yaml_contents),config_changes))
        # would make sense to also check for changes to authorized_keys 
        # would require saving a copy of that some place for comparison
        # xxx todo
        keys_changes = False
        if config_changes or keys_changes:
            # instead of restarting the service we call a companion script
            try:
                fetch_trigger_script_if_missing (slicename)
                # the trigger script actually needs to be run in the slice context of course
                # in addition there is a requirement to pretend we run as a login shell
                # hence sudo -i
                slice_command = [ "sudo", "-i",  omf_rc_trigger_script ]
                to_run = tools.command_in_slice (slicename, slice_command)
                log_filename = "/vservers/%s/%s"%(slicename,omf_rc_trigger_log)
                logger.log("omf_resctl: starting %s"%to_run)
                logger.log("redirected into %s"%log_filename)
                logger.log("*not* waiting for completion..")
                with open(log_filename,"a") as log_file:
                    subprocess.Popen(to_run, stdout=log_file,stderr=subprocess.STDOUT)
                # a first version tried to 'communicate' on that subprocess instance
                # but that tended to create deadlocks in some cases
                # causing nodemanager to stall...
                # we're only losing the child's retcod, no big deal
            except:
                import traceback
                traceback.print_exc()
                logger.log_exc("omf_resctl: WARNING: Could not call trigger script %s"%\
                                   omf_rc_trigger_script, name=slicename)
        else:
            logger.log("omf_resctl: %s: omf_control'ed sliver has no change" % slicename)
