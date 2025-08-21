import pdpyras as pd
import argparse
import sys
import os
from datetime import datetime
import json
import time
import urllib3


params = argparse.ArgumentParser('PagerDuty events')
params.add_argument('--routing_key', type=str.upper, help='Routing Key')
params.add_argument('--msg', type=str, help='Support message (Summary)')
params.add_argument('--source', type=str, help='Server name or program name so on')
params.add_argument('--keyname', type=str, help='Unique Key name for email matching and de-dup')
params.add_argument('--event', type=str.upper, choices=['TRIGGER','RESOLVE','ACKNOWLEDGE'], default= 'TRIGGER',
                    help='Event Type Default: TRIGGER')
params.add_argument('--details', type=str, help='Free text details example "Netbackup appears to be hung on backup-ldn1.\\n Actions:" [Optional]')
params.add_argument('--jdetails', type=str, help='Json dictionary format example: "{\'host\': \'backup-ldn1\'}" [Optional]')
params.add_argument('--jfile', type=str, help='Json File format example: "{\'host\': \'backup-ldn1\'}" [Optional] NOTE: jdetails takes precedence')
params.add_argument('--severity', type=str.lower, choices=['info','critical','warning','error'], help='Select one of the following: info, warning, error, critical Default: critical')
params.add_argument('--retries', type=int, default=3, help='Number of attemps to retry')
params.add_argument('--retry_interval', type=int, choices=[30, 60, 120, 300], default=60, help='Interval between retries in seconds')
params.add_argument('--proxy_server', type=str, help='eg. http://xxx.xxx.xxx.xxx:xxxx')
params.add_argument('--cfgfile', type=str, help='Enter full path and file name')
params.add_argument('--cfgfilekey', type=str, help='Enter cfgfile key')
params.add_argument('--version', action='store_true', help='Information Version')
args = params.parse_args()

realpath = os.path.abspath(os.path.dirname(sys.argv[0]))
log_file = realpath + '/' + datetime.today().strftime('%Y%m%d_%H%M%S') + '_pagerduty.log'
terminal = sys.stdout
#log = open(log_file, 'a')

def logger(msg):
  terminal.write(msg + '\n')
#  log.write(msg + '\n')

def usage():
    params.print_help()
    sys.exit(99)

def chkerr(err):
    print(err.response)
    if int(str(err.response).replace('<Response [', '').replace(']>', '')) >= 500:
        logger(
            'Internal Server Error - the PagerDuty server experienced an error while processing the event.')
    if 'Network Error' in str(err.response):
        logger('Error while trying to communicate with PagerDuty servers.')
    if '400' in str(err.response):
        logger('Invalid event format (i.e. JSON parse error) or incorrect event structure')
        dic = json.loads(err.response.text)
        logger(str(dic['errors']))
        return True
    if '403' in str(err.response):
        logger('Rate limit reached (too many Events API requests)')
    if '429' in str(err.response):
        logger('PagerDuty Busy.')
        time.sleep(120)
    else:
        logger('Unknown error has occurred with resolve.')
    return False
#
# MAIN
#
#
l_routing_key = args.routing_key
l_retries = args.retries
l_retry_interval = args.retry_interval
l_proxy_server = args.proxy_server

if args.version:
    logger("Version 3.0 Nov 2021")
    sys.exit(0)

# Check jfile exists
if args.jfile and args.jdetails:
    logger('Please specify either --jdetails or --jfile not both.')
    usage()

if args.jfile:
    if os.path.isfile(args.jfile):
        with open(args.jfile, 'r') as json_file:
            data = json_file.read()
            chra = chr(0)
            data = data.translate({ord(chra): None})
            data = ''.join(i for i in data if ord(i) < 128)
            data = data.replace('\n\n','\n')
            jsonf = json.loads(data)
    else:
        logger('Jfile not found' + args.jfile)
        usage()

# Check config file entered
if args.cfgfile:
    if args.cfgfilekey:
        if os.path.isfile(args.cfgfile):
            with open(args.cfgfile, 'r') as cfgf:
                data = cfgf.read()
                jobj = json.loads(data)

            # Check if key exist
            try:
                if jobj[args.cfgfilekey]:
                    if not args.routing_key:
                        l_routing_key = jobj[args.cfgfilekey]['routing_key']
                    if not args.retries:
                        l_retries = jobj[args.cfgfilekey]['retries']
                    if not args.retry_interval:
                        l_retry_interval = jobj[args.cfgfilekey]['retry_interval']
                    if not args.proxy_server:
                        l_proxy_server = jobj[args.cfgfilekey]['proxy_server']
                    if not args.severity:
                        l_severity = jobj[args.cfgfilekey]['severity']
                        if not l_severity:
                            l_severity = 'critical'
            except:
                    logger('Config file key not valid')
                    usage()
        else:
            logger('Config file not found')
            usage()
    else:
        logger('Please enter cfgfilekey required when using cfgfile')
        usage()

if not l_routing_key:
    logger('Please enter routing key')
    usage()

session = pd.EventsAPISession(l_routing_key)
if not session:
    logger('Invalid Routing key')
    usage()
if not args.keyname:
    logger("Please enter -keyname")
    usage()
if l_proxy_server:
    urllib3.disable_warnings()
    session.verify = False
    session.proxies = {
        "http": l_proxy_server,
        "https": l_proxy_server
    }
if args.event != 'TRIGGER':
    if args.event == 'RESOLVE':
        logger("Resolve " + args.keyname)
        cnt = 1
        while cnt != l_retries:
            try:
                session.resolve(args.keyname)
                logger('PagerDuty message successfully sent.')
                cnt = 1
                break
            except pd.PDClientError as err:
                if chkerr(err):
                    sys.exit(1)
                cnt += 1
    elif args.event == 'ACKNOWLEDGE':
        logger("Acknowledge " + args.keyname)
        cnt = 1
        while cnt != l_retries:
            try:
                session.acknowledge(args.keyname)
                logger('PagerDuty message successfully sent.')
                cnt = 1
                break
            except pd.PDClientError as err:
                if chkerr(err):
                    sys.exit(1)
                cnt += 1
    else:
        logger('\nPlease enter correct event identifier.\n\n')
        usage()
else:
    if not args.msg:
        logger("Please enter --msg")
        usage()
    if not args.source:
        logger("Please enter --source")
        usage()

    try:
        logger("Trigger " + args.keyname)
        jcdetails = {}
        dwdetails = {}
        jwdetails = {}
        if args.details and args.jdetails:
            dwdetails["Details"] = args.details
            djwdetails = json.loads(args.jdetails.replace('\'','"'))
            djwdetails.update(dwdetails)
            jcdetails.update(djwdetails)
        elif args.details:
            jcdetails["Details"] = json.dumps(args.details)
        elif args.jdetails:
            djwdetails = json.loads(args.jdetails.replace('\'','"'))
            jcdetails.update(djwdetails)
        elif args.jfile and args.jdetails:
            dwdetails["Details"] = args.details
            djwdetails = jsonf
            djwdetails.update(dwdetails)
            jcdetails.update(djwdetails)
        elif args.jfile:
            jcdetails = jsonf
    except:
        logger('Incorrect syntax')
        sys.exit(1)

    cnt = 1
    while cnt != l_retries:
        try:
            session.trigger(summary=args.msg, severity=l_severity, source=args.source, dedup_key=args.keyname,
                            custom_details=jcdetails)
            logger('PagerDuty message successfully sent.')
            cnt = 1
            break
        except pd.PDClientError as err:
            print(err.response)
            if int(str(err.response).replace('<Response [','').replace(']>','')) >= 500:
                logger('Internal Server Error - the PagerDuty server experienced an error while processing the event.')
            if 'Network Error' in str(err.response):
                logger('Error while trying to communicate with PagerDuty servers.')
            if '400' in str(err.response):
                logger('Invalid event format (i.e. JSON parse error) or incorrect event structure')
                dic = json.loads(err.response.text)
                logger(str(dic['errors']))
                break
            if '403' in str(err.response):
                logger('Rate limit reached (too many Events API requests)')
            if '429' in str(err.response):
                logger('PagerDuty Busy.')
                time.sleep(120)
            else:
                logger('Unknown error has occurred.')
            cnt += 1
        logger('Will retry in ' + str(l_retry_interval) + ' secs')
        time.sleep(l_retry_interval)

if cnt == l_retries:
    logger('Failed after ' + str(l_retries) + ' attempts of ' + str(l_retry_interval) + ' secs')
    sys.exit(1)
else:
    sys.exit(0)