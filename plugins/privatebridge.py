#!/usr/bin/python

""" Private Bridge configurator.  """

import httplib
import os
import select
import shutil
import subprocess
import time
import tools

from threading import Thread
import logger
import tools

priority = 9

class OvsException (Exception) :
    def __init__ (self, message="no message"):
        self.message=message
    def __repr__ (self): return message

def start():
    logger.log('private bridge plugin starting up...')

def log_call_read(command,timeout=logger.default_timeout_minutes*60,poll=1):
    message=" ".join(command)
    logger.log("log_call: running command %s" % message)
    logger.verbose("log_call: timeout=%r s" % timeout)
    logger.verbose("log_call: poll=%r s" % poll)
    trigger=time.time()+timeout
    try:
        child = subprocess.Popen(command, bufsize=1,
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE, close_fds=True)

        stdout = ""
        while True:
            # see if anything can be read within the poll interval
            (r,w,x)=select.select([child.stdout],[],[],poll)
            if r: stdout = stdout + child.stdout.read(1)
            # is process over ?
            returncode=child.poll()
            # yes
            if returncode != None:
                stdout = stdout + child.stdout.read()
                # child is done and return 0
                if returncode == 0:
                    logger.log("log_call:end command (%s) completed" % message)
                    if stdout != "":
                        logger.log("log_call:stdout: %s" % stdout)
                    return (returncode, stdout)
                # child has failed
                else:
                    logger.log("log_call:end command (%s) returned with code %d" %(message,returncode))
                    return (returncode, stdout)
            # no : still within timeout ?
            if time.time() >= trigger:
                child.terminate()
                logger.log("log_call:end terminating command (%s) - exceeded timeout %d s"%(message,timeout))
                return (-2, None)
                break
    except:
        logger.log_exc("failed to run command %s" % message)

    return (-1, None)

def ovs_vsctl(args):
    return log_call_read(["ovs-vsctl"] + args)

def ovs_listbridge():
    (returncode, stdout) = ovs_vsctl(["list-br"])
    if (returncode != 0): raise OvsException("list-br")
    return stdout.split()

def ovs_addbridge(name):
    (returncode, stdout) = ovs_vsctl(["add-br",name])
    if (returncode != 0): raise OvsException("add-br")

def ovs_listports(name):
    (returncode, stdout) = ovs_vsctl(["list-ports", name])
    if (returncode != 0): raise OvsException("list-ports")
    return stdout.split()

def ovs_delbridge(name):
    (returncode, stdout) = ovs_vsctl(["del-br",name])
    if (returncode != 0): raise OvsException("del-br")

def ovs_addport(name, portname, type, remoteip, key):
    args = ["add-port", name, portname, "--", "set", "interface", portname, "type="+type]
    if remoteip:
        args = args + ["options:remote_ip=" + remoteip]
    if key:
        args = args + ["options:key=" + str(key)]

    (returncode, stdout) = ovs_vsctl(args)
    if (returncode != 0): raise OvsException("add-port")

def ovs_delport(name, portname):
    (returncode, stdout) = ovs_vsctl(["del-port",name,portname])
    if (returncode != 0): raise OvsException("del-port")

def ensure_slicebridge_created(name, addr):
    bridges = ovs_listbridge()
    logger.log("privatebridge: current bridges = " + ",".join(bridges))
    if name in bridges:
        return

    ovs_addbridge(name)

    logger.log_call(["ifconfig", name, addr, "netmask", "255.0.0.0"])

def ensure_slicebridge_neighbors(name, sliver_id, neighbors):
    ports = ovs_listports(name)

    want_ports = []
    for neighbor in neighbors:
        (neighbor_node_id, neighbor_ip) = neighbor.split("/")
        neighbor_node_id = int(neighbor_node_id)
        portname = "gre%d-%d" % (sliver_id, neighbor_node_id)

        want_ports.append(portname)

        if not portname in ports:
            ovs_addport(name, portname, "gre", neighbor_ip, sliver_id)

    for portname in ports:
        if portname.startswith("gre") and (portname not in want_ports):
            ovs_delport(name, portname)

def configure_slicebridge(sliver, attributes):
    sliver_name = sliver['name']
    sliver_id = sliver['slice_id']

    slice_bridge_name = attributes["slice_bridge_name"]

    slice_bridge_addr = attributes.get("slice_bridge_addr", None)
    if not slice_bridge_addr:
        logger.log("privatebridge: no slice_bridge_addr for %s" % sliver_name)
        return

    slice_bridge_neighbors = attributes.get("slice_bridge_neighbors", None)
    if not slice_bridge_neighbors:
        logger.log("privatebridge: no slice_bridge_neighbors for %s" % sliver_name)
        return

    slice_bridge_neighbors = [x.strip() for x in slice_bridge_neighbors.split(",")]

    ensure_slicebridge_created(slice_bridge_name, slice_bridge_addr)
    ensure_slicebridge_neighbors(slice_bridge_name, sliver_id, slice_bridge_neighbors)

def GetSlivers(data, conf = None, plc = None):
    node_id = tools.node_id()

    if 'slivers' not in data:
        logger.log_missing_data("privatebridge.GetSlivers",'slivers')
        return

    valid_bridges = []
    for sliver in data['slivers']:
        sliver_name = sliver['name']

        # build a dict of attributes, because it's more convenient
        attributes={}
        for attribute in sliver['attributes']:
            attributes[attribute['tagname']] = attribute['value']

        bridge_name = attributes.get('slice_bridge_name',None)
        if bridge_name:
            configure_slicebridge(sliver, attributes)
            valid_bridges.append(bridge_name)

    # now, delete the bridges that we don't want
    bridges = ovs_listbridge()
    for bridge_name in bridges:
        if not bridge_name.startswith("br-slice-"):
            # ignore ones we didn't create
            continue

        if bridge_name in valid_bridges:
            # ignore ones we want to keep
            continue

        logger.log("privatebridge: deleting unused bridge %s" % bridge_name)

        ovs_delbridge(bridge_name)



