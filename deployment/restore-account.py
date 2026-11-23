"""Restore a verified backup to a NEW path; never overwrite a running account."""
import argparse
import hashlib
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))
from operations import backup_database

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('backup',type=Path)
    parser.add_argument('--sha256',required=True)
    parser.add_argument('--destination',type=Path,required=True)
    args=parser.parse_args()
    if args.destination.exists():parser.error('Destination exists; restore to a new path and verify before cutover')
    if not args.backup.is_file() or hashlib.sha256(args.backup.read_bytes()).hexdigest()!=args.sha256:
        parser.error('Backup checksum does not match the trusted manifest')
    print(backup_database(args.backup,args.destination))
