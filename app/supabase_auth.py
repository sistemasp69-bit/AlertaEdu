"""Supabase Auth gateway. No service-role key is used in browser or server.
The backend validates Supabase access tokens before accessing academic data.
"""
import os
import secrets
import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, EmailStr, Field

router = APIRouter(prefix='/api/supabase')
ACCESS_COOKIE='alertaedu_sb_access'
REFRESH_COOKIE='alertaedu_sb_refresh'
CSRF_COOKIE='alertaedu_sb_csrf'


def enabled():
    return os.getenv('ALERTAEDU_AUTH_PROVIDER','supabase').lower() == 'supabase'


def url():
    value=os.getenv('SUPABASE_URL','https://lwjnmebmotcnkjrhhbyl.supabase.co').rstrip('/')
    if not value.startswith('https://'):
        raise RuntimeError('SUPABASE_URL debe usar HTTPS')
    return value


def key():
    value=os.getenv('SUPABASE_PUBLISHABLE_KEY','')
    if not value:
        raise RuntimeError('Configura SUPABASE_PUBLISHABLE_KEY')
    return value


def headers(token=None):
    h={'apikey':key(), 'Content-Type':'application/json'}
    if token: h['Authorization']='Bearer '+token
    return h


def secure():
    return os.getenv('ALERTAEDU_ENV','development').lower()=='production'


def set_cookies(response, data, csrf=None):
    ttl=int(data.get('expires_in') or 3600)
    response.set_cookie(ACCESS_COOKIE,data['access_token'],max_age=ttl,httponly=True,secure=secure(),samesite='lax',path='/')
    if data.get('refresh_token'):
        response.set_cookie(REFRESH_COOKIE,data['refresh_token'],max_age=30*24*3600,httponly=True,secure=secure(),samesite='lax',path='/')
    if csrf:
        response.set_cookie(CSRF_COOKIE,csrf,max_age=30*24*3600,httponly=True,secure=secure(),samesite='lax',path='/')


def clear_cookies(response):
    for cookie in (ACCESS_COOKIE,REFRESH_COOKIE,CSRF_COOKIE): response.delete_cookie(cookie,path='/')


async def supa_post(path, payload, token=None):
    async with httpx.AsyncClient(timeout=12) as client:
        try:
            return await client.post(url()+'/auth/v1/'+path,json=payload,headers=headers(token))
        except httpx.HTTPError:
            raise HTTPException(503,'Servicio de autenticación no disponible')


async def resolve_user(request):
    """Live validation: rejected/expired/revoked access tokens do not authorize data access."""
    token=request.cookies.get(ACCESS_COOKIE)
    refreshed=None
    if token:
        async with httpx.AsyncClient(timeout=12) as client:
            try: response=await client.get(url()+'/auth/v1/user',headers=headers(token))
            except httpx.HTTPError: return None,None
    else: response=None
    if response is None or response.status_code!=200:
        refresh=request.cookies.get(REFRESH_COOKIE)
        if not refresh: return None,None
        r=await supa_post('token?grant_type=refresh_token',{'refresh_token':refresh})
        if r.status_code!=200:return None,None
        refreshed=r.json();token=refreshed['access_token']
        async with httpx.AsyncClient(timeout=12) as client:
            try: response=await client.get(url()+'/auth/v1/user',headers=headers(token))
            except httpx.HTTPError:return None,None
        if response.status_code!=200:return None,None
    user=response.json()
    if not user.get('id') or not user.get('email_confirmed_at'):return None,None
    # Never trust user_metadata for roles; use server-side auth_roles.
    from app.main import conn
    with conn() as c:
        row=c.execute('SELECT role FROM auth_roles WHERE user_id=?',(user['id'],)).fetchone()
    role=row['role'] if row else 'Usuario'
    return {'username':user['email'],'role':role,'csrf_token':request.cookies.get(CSRF_COOKIE,''),'auth_user_id':user['id'],'access_token':token},refreshed


class Credentials(BaseModel):
    email: EmailStr
    password: str=Field(min_length=8,max_length=128)

class EmailOnly(BaseModel):
    email: EmailStr


@router.get('/config')
def public_config():
    return {'url':url(),'publishableKey':key(),'provider':'supabase'}


@router.post('/register')
async def register(form:Credentials):
    # Public signups cannot create administrators; the auth_roles table defaults to Usuario.
    r=await supa_post('signup',{'email':str(form.email),'password':form.password})
    # Do not expose whether an address is already registered.
    if r.status_code in (200,201,400,422):
        return {'message':'Si es posible registrar este correo, recibirás instrucciones para verificarlo.'}
    raise HTTPException(503,'No se pudo procesar la solicitud. Intenta más tarde.')


@router.post('/login')
async def login(form:Credentials):
    r=await supa_post('token?grant_type=password',{'email':str(form.email),'password':form.password})
    if r.status_code!=200:raise HTTPException(401,'Correo o contraseña incorrectos, o correo sin verificar')
    data=r.json()
    async with httpx.AsyncClient(timeout=12) as client:
        user_resp=await client.get(url()+'/auth/v1/user',headers=headers(data['access_token']))
    if user_resp.status_code!=200 or not user_resp.json().get('email_confirmed_at'):
        raise HTTPException(401,'Verifica tu correo antes de ingresar')
    from app.main import conn
    with conn() as c:
        row=c.execute('SELECT role FROM auth_roles WHERE user_id=?',(user_resp.json()['id'],)).fetchone()
    csrf=secrets.token_urlsafe(32)
    res=JSONResponse({'ok':True,'role':row['role'] if row else 'Usuario'})
    set_cookies(res,data,csrf)
    return res


@router.post('/forgot')
async def forgot(form:EmailOnly):
    base=os.getenv('ALERTAEDU_BASE_URL','').rstrip('/')
    if not base:
        base=os.getenv('RENDER_EXTERNAL_URL','').rstrip('/') or 'http://127.0.0.1:8000'
    redirect=base+'/reset-password'
    # GoTrue receives redirect_to query param; no email enumeration on response.
    async with httpx.AsyncClient(timeout=12) as client:
        try:
            await client.post(url()+'/auth/v1/recover',params={'redirect_to':redirect},json={'email':str(form.email)},headers=headers())
        except httpx.HTTPError: pass
    return {'message':'Si el correo tiene una cuenta, recibirás un enlace para restablecer la contraseña.'}


@router.post('/logout')
async def logout(request:Request):
    token=request.cookies.get(ACCESS_COOKIE)
    if token:
        try: await supa_post('logout',{},token)
        except Exception: pass
    res=JSONResponse({'ok':True})
    clear_cookies(res)
    return res

async def change_password(request,current_password,new_password):
    user=request.state.user
    test=await supa_post('token?grant_type=password',{'email':user['username'],'password':current_password})
    if test.status_code != 200:
        raise HTTPException(401,'La contraseña actual no es correcta')
    if current_password == new_password or len(new_password) < 12:
        raise HTTPException(422,'Usa una contraseña nueva de al menos 12 caracteres')
    r=await supa_post('user',{'password':new_password},user['access_token'])
    if r.status_code != 200:
        raise HTTPException(503,'No se pudo actualizar la contraseña')
    res=JSONResponse({'changed':True,'message':'Contraseña actualizada. Vuelve a iniciar sesión.'})
    clear_cookies(res)
    return res
