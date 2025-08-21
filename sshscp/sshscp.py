import paramiko
import json
import subprocess
import argparse
import logging
import os, sys
import socket
from io import StringIO

parser = argparse.ArgumentParser()
parser.add_argument('--host', required=True, type=str, help='Remote hosts')
parser.add_argument('--key', required=True, type=str, help='Key name')
parser.add_argument('--vault', required=False, type=str, default='AKV-MSGB-MGT01-LINUX', help='Key vault name')
parser.add_argument('--cmd', required=False, type=str, help='Remote cmd/cmds to execute after file/folder transfer if applicable')
parser.add_argument('--folder', required=False, type=str, help='Folder to transfer to remote host')
parser.add_argument('--rmtfolder',required=False, type=str, help='Destination on remote host')
parser.add_argument('--file', required=False, type=str, help='Single file to transfer to remote host')
parser.add_argument('--rmtfile',required=False, type=str, help='File destination on remote host')
parser.add_argument('--chrcode', required=False, type=str, default='windows-1252', help='Data decode. Default windows-1252 for windows, utf-8 for Linux')
parser.add_argument('--logdir', required=False, type=str, default='./log', help='Log directory. Default ./log')
parser.add_argument('--rmtuser', required=False, type=str, default='azadmin', help='Remote target user for connection. Default ec2-user')
args = parser.parse_args()

def eprint(*args, **kwargs):
    print(*args, file=sys.stderr, **kwargs)
    print(*args)

def key_based_connect(host, key, rmtuser, vault):
    try:
        spath = os.path.dirname(__file__)
        subcmd = 'az keyvault secret show --name "' + key + '" --vault-name ' + vault
        if args.rmtuser:
            special_account = rmtuser
        else:
            special_account = "azadmin"
        key_string = dict()
        # Get key
        p = subprocess.Popen(subcmd, stdout=subprocess.PIPE, shell=True)
        (output, err) = p.communicate()  
        p_status = p.wait()
        data = output.decode(chrcode)
        key_string = json.loads(data, strict=False)
        file_obj = StringIO(key_string['value'])
        pkey = paramiko.RSAKey.from_private_key(file_obj)
        ssh = paramiko.SSHClient()
        policy = paramiko.AutoAddPolicy()
        ssh.set_missing_host_key_policy(policy)
        ssh.connect(host, username=special_account, pkey=pkey)
        return ssh
    except paramiko.ssh_exception.SSHException as e:
        logging.error(f"SCPException during connection: {e}")
        raise
    except:
        logging.error("Exception during connection")
        raise

def remotepath_join(self,*args):
    return '/'.join(args)

def bulk_upload(filepaths, remotepath, ssh):
    try:
        dummy=''
        scp = ssh.open_sftp()
        os.chdir(os.path.split(filepaths)[0])
        parent=os.path.split(filepaths)[1]
        for path,_,files in os.walk(parent):
            logging.info(f"Starting uploading {path} files to {remotepath} on {host}")
            try:
                scp.mkdir(remotepath_join(dummy,remotepath,path))
            except:
                pass
            for filename in files:
                scp.put(os.path.join(path,filename),remotepath_join(dummy,remotepath,path,filename))
            logging.info(f"Finished uploading {path} files to {remotepath} on {host}")
        scp.close()
    except paramiko.ssh_exception.SSHException as e:
        logging.error(f"SCPException during bulk upload: {e}")

def single_file(srcfile, rmtfile, ssh):
    try:
        scp = ssh.open_sftp()
        scp.put(srcfile, rmtfile)
        scp.close()
        logging.info(f"Finished uploading {srcfile} to {rmtfile} on {host}")
    except paramiko.ssh_exception.SSHException as e:
        logging.error(f"SCPException during file upload: {e}")

def run_cmd(cmd, ssh):
    try:
        logging.info(f"{cmd}")
        stdin, stdout, stderr = ssh.exec_command(f"{cmd}")
        if stdout.channel.recv_exit_status()  == 0:
            try:
                output = stdout.read().decode(chrcode)
            except:
                output = stdout.read()
            logging.info(output)
            return output
        else:
            outerr = stderr.read().decode(chrcode)
            output = stdout.read().decode(chrcode)
            logging.error(outerr)
            logging.error(output)
            eprint(outerr)
            sys.exit(1)

    except paramiko.ssh_exception.SSHException as e:
        logging.error(f"SSHException: {e}")

  
# Main

# Validation of parameters
if not args.folder and not args.file and not args.cmd:
    print(f"Please specify action required")
    sys.exit(1)

if args.folder and args.file:
    print(f"Please specify either --folder or --file")
    sys.exit(1)

if args.folder:
    if os.path.exists(args.folder) and os.path.isdir(args.folder):
        logging.info(f"Folder exists {args.folder}")
        # Check rmt parameer has value
        if not args.rmtfolder:
            print(f"Remote folder parameter required --rmtfolder")
            sys.exit(1) 
    else:
        print(f"Source folder {args.folder} does not exists")
        sys.exit(1)

if args.file:
    if os.path.exists(args.file) and not os.path.isdir(args.file):
        logging.info(f"File exists {args.file}")
        if not args.rmtfile:
            print(f"Remote file parameter required --rmtfile")
            sys.exit(1) 
    else:
        print(f"Source folder {args.file} does not exists")
        sys.exit(1)

global host
global chrcode
host = args.host

if args.chrcode == 'windows-1252':
    # Check os
    if sys.platform == 'Linux':
        chrcode = 'utf-8'
    else:
        chrcode = args.chrcode

# Check log directory exists
if os.path.exists(args.logdir) and os.path.isdir(args.logdir):
    LOGDIR = args.logdir
    logfile = LOGDIR + '/sshscp_' + args.host + '.log'
    logging.basicConfig(level=logging.INFO, filename=logfile, filemode="a+",
                        format="%(asctime)-15s %(levelname)-8s %(message)s")
else:
    print(f"Log path {args.logdir} does not exists")
    sys.exit(1)

# Check host
if socket.gethostbyname(host):
    logging.info(f"Host found {host}")
else:
    logging.error(f"Host not found {host}")
    sys.exit(1)

# Execute request
logging.info(f"Connecting to remote host {host}")
ssh = key_based_connect(host, args.key, args.rmtuser, args.vault)

if args.file:
    single_file(args.file, args.rmtfile, ssh)
    
if args.folder:
    bulk_upload(args.folder, args.rmtfolder, ssh)

if args.cmd:
    result = run_cmd(args.cmd, ssh)
    print(result)

ssh.close()
logging.shutdown()