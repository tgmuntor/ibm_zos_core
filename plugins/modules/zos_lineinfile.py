#!/usr/bin/python
# -*- coding: utf-8 -*-

# Copyright (c) IBM Corporation 2019, 2020
# Apache License, Version 2.0 (see https://opensource.org/licenses/Apache-2.0)


from __future__ import absolute_import, division, print_function
__metaclass__ = type

ANSIBLE_METADATA = {'metadata_version': '1.1',
                    'status': ['preview'],
                    'supported_by': 'community'}


DOCUMENTATION = r'''
---
module: zos_lineinfile
short_description: Manage lines in zos uss files or partitioned dataset members 
or sequential datasets
description:
  - This module ensures a particular line is in a uss file or dataset, or
  replace an existing line using a back-referenced regular expression.
  - This is primarily useful when you want to change a single line in a uss 
  file or dataset only.
options:
  zosdest:
    description:
      - The zos uss file or dataset to modify.
    type: str
    required: true
  regexp:
    description:
      - The regular expression to look for in every line of the uss file
      or dataset.
      - For C(state=present), the pattern to replace if found. Only the
      last line found will be replaced.
      - For C(state=absent), the pattern of the line(s) to remove.
      - If the regular expression is not matched, the line will be
        added to the file in keeping with C(insertbefore) or C(insertafter)
        settings.
      - When modifying a line the regexp should typically match both
      the initial state of the line as well as its state after replacement by
      C(line) to ensure idempotence.
      - Uses Python regular expressions. See U(http://docs.python.org/2/library/re.html).
    type: str
  state:
    description:
      - Whether the line should be there or not.
    type: str
    choices: [ absent, present ]
    default: present
  line:
    description:
      - The line to insert/replace into the uss file or dataset.
      - Required for C(state=present).
      - If C(backrefs) is set, may contain backreferences that will get
        expanded with the C(regexp) capture groups if the regexp matches.
    type: str
    aliases: [ value ]
  backrefs:
    description:
      - Used with C(state=present).
      - If set, C(line) can contain backreferences (both positional and named)
        that will get populated if the C(regexp) matches.
      - This parameter changes the operation of the module slightly;
        C(insertbefore) and C(insertafter) will be ignored, and if the 
        C(regexp) does not match anywhere in the file, the file will be left unchanged.
      - If the C(regexp) does match, the last matching line will be replaced by
        the expanded line parameter.
    type: bool
    default: no
  insertafter:
    description:
      - Used with C(state=present).
      - If specified, the line will be inserted after the last match of specified regular expression.
      - If the first match is required, use(firstmatch=yes).
      - A special value is available; C(EOF) for inserting the line at the end of the file.
      - If specified regular expression has no matches, EOF will be used instead.
      - If C(insertbefore) is set, default value C(EOF) will be ignored.
      - If regular expressions are passed to both C(regexp) and C(insertafter), C(insertafter) is only honored if no match for C(regexp) is found.
      - May not be used with C(backrefs) or C(insertbefore).
    type: str
    choices: [ EOF, '*regex*' ]
    default: EOF
  insertbefore:
    description:
      - Used with C(state=present).
      - If specified, the line will be inserted before the last match of specified regular expression.
      - If the first match is required, use C(firstmatch=yes).
      - A value is available; C(BOF) for inserting the line at the beginning of the uss file or dataset.
      - If specified regular expression has no matches, the line will be inserted at the end of the file.
      - If regular expressions are passed to both C(regexp) and C(insertbefore), C(insertbefore) is only honored if no match for C(regexp) is found.
      - May not be used with C(backrefs) or C(insertafter).
    type: str
    choices: [ BOF, '*regex*' ]
  backup:
    description:
      - Create a backup file or dataset including the timestamp information so you can
        get the original file back if you somehow clobbered it incorrectly.
    type: bool
    default: no
  backupdest:
    description:
      - The file destination or dataset name for backup
    type: str
  firstmatch:
    description:
      - Used with C(insertafter) or C(insertbefore).
      - If set, C(insertafter) and C(insertbefore) will work with the first line that matches the given regular expression.
    type: bool
    default: no
  encoding:
    description:
      - Specifies which encodings the fetched data set should be converted from
        and to. If this parameter is not provided, this module assumes that
        source file or data set is encoded in IBM-1047 and will be converted
        to ISO8859-1.
    required: false
    type: dict
    suboptions:
      from:
        description: The encoding to be converted from
        required: true
        type: str
      to:
        description: The encoding to be converted to
        required: true
        type: str
    default: { from: 'IBM-1047', to: 'ISO8859-1' }
'''

EXAMPLES = r'''
- name: Ensure dataset for cics SIT input has the SEC setting as YES
  lineinfile:
    path: XIAOPIN.TEST.TXT(SIT)
    regexp: '^SEC='
    line: SEC=YES

- name: Remove the encoding configuration in liberty profiles
  lineinfile:
    path: /samples/cicswlp_oci/LIBERTY.jvmprofile
    state: absent
    regexp: '^%encoding'

- name: Ensure the liberty https port is 8080
  lineinfile:
    path: /samples/cicswlp_oci/LIBERTY.jvmprofile
    regexp: '^Listen '
    insertafter: '^#Listen '
    line: Listen 8080

- name: Ensure we have our own comment added to CICS SIT member
  lineinfile:
    path: XIAOPIN.TEST.TXT(SIT)
    regexp: '#^SEC='
    insertbefore: '^SEC='
    line: '# security configuration by default'

- name: Ensure the user working directory for liberty is set as needed
  lineinfile:
    path: /samples/cicswlp_oci/LIBERTY.jvmprofile
    regexp: '^(.*)User(\d+)m(.*)$'
    line: '\1APPUser\3'
    backrefs: yes

'''

import os
import argparse
import re
import tempfile

# import module snippets
from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils.better_arg_parser import BetterArgParser
from zoautil_py import Datasets

def main():
    module = AnsibleModule(
        argument_spec=dict(
            zosdest=dict(type='path', required=True),
            state=dict(type='str', default='present', choices=['absent', 'present']),
            regexp=dict(type='str'),
            line=dict(type='str'),
            insertafter=dict(type='str'),
            insertbefore=dict(type='str'),
            backrefs=dict(type='bool', default=False),
            backup=dict(type='bool', default=False),
            firstmatch=dict(type='bool', default=False),
            encoding=dict(
                required=False,
                type=dict,
                default={'from': 'IBM-1047', 'to': 'ISO8859-1'}
            ),
        ),
      ),
    arg_defs = dict(
        zosdest=dict(
            arg_type=data_set_or_path_type, 
            required=True，
            ),
        state=dict(
            arg_type='str', 
            default='present', 
            choices=['absent', 'present']
            ),
        regex=dict(
            arg_type=regex_type,
            ),
        line=dict(
            arg_type='str',
        ),
        insertafter=dict(
            arg_type='str',
            mutually_exclusive=['insertbefore']
            default=eof_tbd
            ),
        insertbefore=dict(
            arg_type='str',
            mutually_exclusive=['insertafter']
            ),
        backrefs=dict(
            arg_type='bool',
            dependencies=['regex'],
            default=False，
            ),
        backup=dict(
            arg_type='bool',
            default=False
            ),
        firstmatch=dict(
            arg_type='bool',
            default=False
            ),
        encoding=dict(
            arg_type='dict',
            default={'from': 'IBM-1047', 'to': 'ISO8859-1'}
            ),
    )
    parser = BetterArgParser(arg_defs)
    params = parser.parse_args(module.params)
    backup = params['backup']
    backrefs = params['backrefs']
    zosdest = params['zosdest']
    firstmatch = params['firstmatch']
    regexp = params['regexp']
    line = params['line']
    ins_aft = params['insertafter']
    ins_bef = params['insertbefore']
    # analysis the file type
    file_type = ds_utils.get_data_set_type()
    if new_params['state'] == 'present':
        if line is None:
            module.fail_json(msg='line is required with state=present')
        present(zosdest, regexp, line,
                ins_aft, ins_bef, backup, backrefs, firstmatch,file_type,encoding)
    else:
        if regexp is None and line is None:
            module.fail_json(msg='one of line or regexp is required with state=absent')
        absent(path, regexp, line, backup,file_type)


if __name__ == '__main__':
    main()

def data_set_or_path_type(contents, dependencies):
    if not re.fullmatch(
        r"^(?:(?:[A-Z]{1}[A-Z0-9]{0,7})(?:[.]{1})){1,21}[A-Z]{1}[A-Z0-9]{0,7}(?:\([A-Z]{1}[A-Z0-9]{0,7}\)){0,1}$",
        str(contents),
        re.IGNORECASE,
    ):
        if not path.isabs(str(contents)):
            raise ValueError(
                'Invalid argument type for "{0}". expected "data_set" or "path"'.format(
                    contents
                )
            )
    return str(contents)

def encoding_type(contents, dependencies):
    if not re.fullmatch(r"^[A-Z0-9-]{2,}$", str(contents), re.IGNORECASE,):
        raise ValueError(
            'Invalid argument type for "{0}". expected "encoding"'.format(contents)
        )
    return str(contents)


def present(zosdest, regexp, line,
                ins_aft, ins_bef, backup, backrefs, firstmatch,file_type,encoding):
    if file_type == 'uss':
      filetype=1
        # todo
    else:
      filetype=0
    Datasets.datasets_ensure_line_present(zosdest, line, regexp, insertAfter, insertBefore, encoding, backup, firstMatch, backref,filetype)

def absent(zosdest, regexp, line, backup,file_type):
    if file_type == 'uss':
        filetype=1
    else:
        filetype=0
        Datasets.datasets_ensure_line_absent(zosdest, regexp, line, backup,filetype)