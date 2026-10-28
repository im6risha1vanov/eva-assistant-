"""Strict read endpoint allowlist. AlphaCRM uses POST for read/index methods too."""
from __future__ import annotations

import json
import time
from pathlib import Path
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen
from urllib.error import HTTPError

READ_CONTROLLERS = frozenset({'branch','group','cgi','lesson','regular-lesson','room','location','teacher','subject'})


class CRMError(Exception):
    pass


def config_from_file(path):
    result={}
    for line in Path(path).read_text(encoding='utf-8-sig').splitlines():
        if '=' in line and not line.lstrip().startswith('#'):
            key,value=line.split('=',1);result[key.strip()]=value.strip().strip('"\'')
    return result


class ReadOnlyCRM:
    def __init__(self,config,transport=urlopen):
        self.base=config['ALFACRM_BASE_URL'].rstrip('/')
        parsed=urlsplit(self.base)
        if parsed.scheme!='https' or parsed.hostname!='kodologiyapiksel.s20.online' or parsed.path or parsed.query or parsed.fragment or parsed.username or parsed.port not in {None,443}:
            raise CRMError('Unexpected CRM host')
        self.email=config['ALFACRM_EMAIL'];self.key=config['ALFACRM_API_KEY']
        if not self.email or not self.key: raise CRMError('Missing CRM configuration')
        self.transport=transport;self.token=None;self.last_request=0
        self.requests=[]

    def _post(self,path,body,authenticated=True):
        # Validate again at the transport boundary. No general-purpose write method exists.
        route=urlsplit(path)
        parts=route.path.strip('/').split('/')
        login=path=='/v2api/auth/login'
        valid_read=(parts[0:1]==['v2api'] and parts[-1:] == ['index'] and
                    ((len(parts)==3 and parts[1]=='branch') or
                     (len(parts)==4 and parts[1].isdigit() and int(parts[1])>0 and parts[2] in READ_CONTROLLERS)))
        if not (login or valid_read) or route.scheme or route.netloc or route.fragment:
            raise CRMError('Blocked non-read CRM endpoint')
        if route.query and (len(parts)!=4 or parts[2]!='cgi' or not route.query.startswith('group_id=') or not route.query.removeprefix('group_id=').isdigit()):
            raise CRMError('Blocked CRM query')
        if not isinstance(body,dict): raise CRMError('Invalid read filter')
        delay=0.26-(time.monotonic()-self.last_request)
        if delay>0: time.sleep(delay)
        self.last_request=time.monotonic()
        headers={'Content-Type':'application/json','Accept':'application/json'}
        if authenticated: headers['X-ALFACRM-TOKEN']=self.token
        request=Request(self.base+path,data=json.dumps(body).encode(),headers=headers,method='POST')
        self.requests.append(route.path)
        try:
            with self.transport(request,timeout=25) as response:
                result=json.load(response)
        except HTTPError as exc:
            raise CRMError('CRM_HTTP_'+str(exc.code)) from None
        except Exception as exc:
            raise CRMError('CRM_'+type(exc).__name__) from None
        if not isinstance(result,dict): raise CRMError('Invalid CRM response')
        return result

    def login(self):
        result=self._post('/v2api/auth/login',{'email':self.email,'api_key':self.key},authenticated=False)
        self.token=result.get('token')
        if not isinstance(self.token,str) or not self.token: raise CRMError('CRM authorization failed')

    def index(self,controller,branch=None,filters=None,group_id=None):
        if controller not in READ_CONTROLLERS: raise CRMError('Blocked CRM controller')
        if branch is None:
            if controller!='branch': raise CRMError('Branch required')
            path='/v2api/branch/index'
        else:
            if type(branch)!=int or branch<=0: raise CRMError('Invalid branch')
            path=f'/v2api/{branch}/{controller}/index'
        if group_id is not None:
            if controller!='cgi' or type(group_id)!=int or group_id<=0: raise CRMError('Invalid group filter')
            path+='?'+urlencode({'group_id':group_id})
        if self.token is None: self.login()
        body=dict(filters or {})
        try: result=self._post(path,body)
        except CRMError as exc:
            if str(exc)!='CRM_HTTP_401': raise
            self.login();result=self._post(path,body)
        if not isinstance(result.get('items'),list) or type(result.get('total'))!=int:
            raise CRMError('Incomplete CRM listing')
        return result

    def all(self,controller,branch=None,filters=None,group_id=None):
        items=[];seen=set()
        for page in range(100):
            result=self.index(controller,branch,dict(filters or {},page=page,pageSize=500),group_id)
            rows=result['items']
            for row in rows:
                if not isinstance(row,dict) or 'id' not in row: raise CRMError('Invalid CRM row')
                if row['id'] in seen: raise CRMError('Repeated CRM page')
                seen.add(row['id']);items.append(row)
            if len(items)>=result['total']:
                if len(items)!=result['total']: raise CRMError('CRM total changed during read')
                return items
            if not rows: raise CRMError('Truncated CRM listing')
        raise CRMError('CRM page limit exceeded')
