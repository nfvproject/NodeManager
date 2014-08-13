#!/usr/bin/python
#
# Parses the PLC configuration file /etc/planetlab/plc_config, which
# is bootstrapped by Boot Manager, but managed by us.
#
# Mark Huang <mlhuang@cs.princeton.edu>
# Copyright (C) 2006 The Trustees of Princeton University
#

import os

class Node_Config:
    """
    Parses Python configuration files; all variables in the file are
    assigned to class attributes.
    """

    def __init__(self, file = "/etc/planetlab/node_config"):
        try:
            execfile(file, self.__dict__)
        except:
            raise Exception, "Could not parse " + file

if __name__ == '__main__':
    from pprint import pprint
    for (k,v) in Config().__dict__.iteritems():
        if k not in ['__builtins__']:
            pprint ( (k,v), )
