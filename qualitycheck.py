#!/usr/bin/env python3
# coding=UTF-8
"""Quality check for RINEX observation files using TEQC software,
print primary marks of data quality. Using concurent.futures.

The RINEX file quality check function rely on TEQC software, Check if
you have installed TEQC by typing `teqc -help` in cmd.

:author: Jon Jiang
:email: jiangyingming@live.com
"""
from concurrent import futures
import argparse
import datetime
import glob
import itertools
import os
import subprocess

MAX_THREADING = max(6, os.cpu_count())
QUALITYINFO = (
    {'name': 'start', 'flag': 'Time of start of window :', 'pos': slice(25, 51)},
    {'name': 'end', 'flag': 'Time of  end  of window :', 'pos': slice(37, 51)},
    {'name': 'length', 'flag': 'Time line window length :', 'pos': slice(26, 42)},
    {'name': 'SN1', 'flag': 'Mean S1                 :', 'pos': slice(26, 31)},
    {'name': 'SN2', 'flag': 'Mean S2                 :', 'pos': slice(26, 31)}
)


def quality_check(src_file):
    """Run quality check for source file using TEQC software.

    1. If run TEQC successfully, return quality check report;
    2. If run TEQC failed, return None.
    """
    args = 'teqc', '+qc', '-plot', '-rep', src_file
    status, output = subprocess.getstatusoutput(' '.join(args))
    # if exit status of TEQC software is not 0, means error
    if status > 0:
        return None

    return output.split('\n')


def parse_report(report):
    """Parse TEQC quality check report, return a tuple:
    (date, start, end, length, SN1, SN2, MP1, MP2, CSR).

    Example:

    >>> report = [
    ... 'Time of start of window : 2017 Aug 10  00:00:00.000',
    ... 'Time of  end  of window : 2017 Aug 10  23:59:30.000',
    ... 'Time line window length : 23.99 hour(s), ticked every ...',
    ... 'Mean S1                 : 46.95 (sd=5.80 n=49483)',
    ... 'Mean S2                 : 42.21 (sd=8.18 n=48411)',
    ... '      first epoch    last epoch    hrs   dt  #expt  #have   %'
    ... '   mp1   mp2 o/slps',
    ... 'SUM 17  8 10 00:00 17  8 10 23:59 24.00  30     -   47669  - '
    ... '  0.43  0.42   3972'
    ... ]
    >>> result = parse_report(report) # doctest: +NORMALIZE_WHITESPACE
    >>> result[0:4]
    ('2017-08-10', '00:00:00.000', '23:59:30.000', '23.99 hour(s)')
    >>> [round(num, 2) for num in result[4:]]
    [46.95, 42.21, 0.43, 0.42, 0.25]
    """
    # because the order of output messages are same, so we only need to
    # check the segment once.
    marks, last_no = {}, 0
    for item in QUALITYINFO:
        for number, line in enumerate(report[last_no:], last_no):
            if item['flag'] not in line:
                continue
            marks[item['name']] = line[item['pos']].strip()
            last_no = number
            break
    # restruct the quality marks into a tuple
    sn1, sn2 = float(marks['SN1']), float(marks['SN2'])
    date = datetime.datetime.strptime(marks['start'][0:11], '%Y %b %d')
    start, end = marks['start'][11:].strip(), marks['end']
    length = marks['length'].split(',')[0]
    # get MP1, MP2, CSR from the last line of report
    last_line = report[-1]
    mp1, mp2 = float(last_line[63:67]), float(last_line[69:73])
    olps = float(last_line[75:])
    csr = 1000 / olps

    result = (date.strftime('%Y-%m-%d'), start, end,
              length, sn1, sn2, mp1, mp2, csr)

    return result


def print_marks(marks, out_fmt):
    """Print marks of quality check, the out_fmt is list or table."""
    if out_fmt == 'list' or out_fmt == 'l':
        message = ('\n{0} quality marks:\n' 'date: {1}\n' 'start: {2}\n'
                   'end: {3}\n' 'length: {4}\n' 'SN1: {5:.2f}\n'
                   'SN2: {6:.2f}\n' 'MP1: {7:.2f}\n' 'MP2: {8:.2f}\n'
                   'CSR: {9:.2f}')
        print(message.format(*marks))
    else:
        message = ('{0: ^14s} {1: ^12s} {2: ^14s} {3: ^14s} {4: ^15s}  '
                   '{5: 6.2f}  {6: 6.2f}  {7: 6.2f}  {8: 6.2f}  {9: 5.2f}')
        print(message.format(os.path.basename(marks[0]), *marks[1:]))


def parallel_teqc(src_files, out_fmt):
    """Parallel run function using argvs."""
    with futures.ThreadPoolExecutor(max_workers=MAX_THREADING) as executor:
        todo_map = {}
        for src_file in src_files:
            future = executor.submit(quality_check, src_file)
            todo_map[future] = src_file
        task_iter = futures.as_completed(todo_map)
        failed_files = []
        for future in task_iter:
            src_file = todo_map[future]
            # return None means task is success
            res = future.result()
            if res:
                record = (src_file, *parse_report(res))
                print_marks(record, out_fmt)
            else:
                failed_files.append(os.path.basename(src_file))

    return failed_files


def init_args():
    """Initilize function, parse user input"""
    # initilize a argument parser
    parser = argparse.ArgumentParser(
        description="Quality check for RINEX observation files using TEQC."
    )
    # add arguments
    parser.add_argument('-v', '--version', action='version',
                        version='%(prog)s 0.4.0')
    parser.add_argument('-r', '--recursive', action='store_true',
                        help='search file recursively')
    parser.add_argument('-out', metavar='<format>', default='table',
                        choices=['list', 'l', 'table', 't'],
                        help='output format, list or table [default: table]')
    parser.add_argument('files', metavar='<file>', nargs='+',
                        help='file will be processed')

    return parser.parse_args()


def main():
    """Main function."""
    args = init_args()
    globstrs, out_fmt, recursive = args.files, args.out, args.recursive
    # collect input globstrs into a glob list
    globs = [glob.iglob(globstr, recursive=recursive) for globstr in globstrs]
    src_files = [src for src in itertools.chain(*globs)]
    # make input args for teqc function
    print('Start processing: {} ...'.format(', '.join(globstrs)))
    # if output format is table, print a table header first
    if out_fmt == 'table' or out_fmt == 't':
        header = ('file', 'date', 'start', 'end', 'length',
                  'SN1', 'SN2', 'MP1', 'MP2', 'CSR')
        style = ('\n{0: ^14s} {1: ^12s} {2: ^14s} {3: ^14s} {4: ^15s} '
                 '{5: >6s}  {6: >6s}  {7: >6s}  {8: >6s}  {9: >5s}')
        print(style.format(*header))
    # start parallel processing
    failed = parallel_teqc(src_files, out_fmt)
    if failed:
        print('\nQuality check failed files: {}'.format(', '.join(failed)))

    return 0


if __name__ == '__main__':
    main()
