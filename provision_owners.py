"""Provision the two requested owners. Emit secrets only to the calling operator."""
import argparse
import json
from pathlib import Path
import secrets
import sys

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'hub-core'))
from grainguard_hub.auth import AuthStore


def make_password(prefix):
    alphabet='ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789'
    return prefix+'-'+''.join(secrets.choice(alphabet) for _ in range(7))+'-'+''.join(secrets.choice(alphabet) for _ in range(7))


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--data-dir',required=True)
    parser.add_argument('--detach-pumpkintec-phone',action='store_true')
    args=parser.parse_args()
    store=AuthStore(args.data_dir)
    result=[]
    for username,site,name,prefix in [
        ('pumpkintec','pumpkintec','PumpkinTec','Ptk'),
        ('uengliangseng','uengliangseng','โรงสีไฟอึ้งเลี่ยงเส็ง','Mill'),
    ]:
        password=make_password(prefix)
        user_id=store.provision_site_owner(username,password,name,site)
        with store.db() as db:
            if username=='pumpkintec' and args.detach_pumpkintec_phone:
                db.execute('UPDATE users SET phone=NULL WHERE id=? AND username=?',(user_id,username))
            phone_linked=bool(db.execute('SELECT phone IS NOT NULL FROM users WHERE id=?',(user_id,)).fetchone()[0])
        result.append({'username':username,'password':password,'site_id':site,'name':name,
                       'user_id':user_id,'phone_linked':phone_linked})
    print(json.dumps(result,ensure_ascii=False))


if __name__=='__main__':main()
