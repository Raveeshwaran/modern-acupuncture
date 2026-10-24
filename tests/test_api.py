import json,sqlite3
from datetime import date,timedelta
import pytest
from app import create_app

@pytest.fixture(scope='session')
def app(tmp_path_factory):
    d=tmp_path_factory.mktemp('care-test')
    import os
    os.environ['DATA_DIR']=str(d)
    return create_app({'TESTING':True,'DATABASE':str(d/'test.sqlite3'),'DEMO_MODE':True})

@pytest.fixture
def client(app): return app.test_client()

def call(c,path,method='GET',data=None):
    token=c.get('/api/bootstrap').json['csrf']
    return c.open('/api/'+path,method=method,json=data,headers={'X-CSRF-Token':token})

def login(c,role='patient',n=1):
    return call(c,'login','POST',{'email':'patient@example.com' if role=='patient' else f'doctor{n:02d}@example.com','password':'DemoCare!2026','role':role,'card':f'ACU-DEMO-{n:03d}'})

def test_directory_exactly_forty(client):
    r=call(client,'doctors'); assert r.status_code==200 and len(r.json['doctors'])==40
    assert all(d['sample'] for d in r.json['doctors'])

def test_authentication_required(client):
    for path in ['intake','notes','messages','patients','appointments','export']:
        assert call(client,path).status_code==401

def test_csrf_required(client):
    client.get('/api/bootstrap');r=client.post('/api/login',json={'email':'patient@example.com'})
    assert r.status_code==403

def test_patient_signin(client):
    r=login(client);assert r.status_code==200;assert r.json['user']['doctor']['id']==1
    assert 'password' not in r.json['user']

def test_wrong_doctor_card(client):
    r=call(client,'login','POST',{'email':'doctor01@example.com','password':'DemoCare!2026','role':'doctor','card':'wrong'})
    assert r.status_code==401

def test_doctor_needs_password(client):
    r=call(client,'login','POST',{'email':'doctor01@example.com','password':'wrong','role':'doctor','card':'ACU-DEMO-001'})
    assert r.status_code==401

def test_patient_cannot_select_doctor_role(client):
    r=call(client,'login','POST',{'email':'patient@example.com','password':'DemoCare!2026','role':'doctor','card':'ACU-DEMO-001'})
    assert r.status_code==401

def test_register_assign_and_no_escalation(client):
    r=call(client,'register','POST',{'name':'New Sample','email':'new-sample@example.com','password':'NewSamplePass!2026','consent':True,'role':'doctor','doctor_id':1})
    assert r.status_code==200 and r.json['user']['role']=='patient'
    assert r.json['user']['doctor_id']==2
    assert call(client,'register','POST',{'name':'New Sample','email':'NEW-SAMPLE@example.com','password':'NewSamplePass!2026','consent':True}).status_code==409

def test_gender_and_dob_not_required(client):
    login(client)
    r=call(client,'intake','PUT',{'data':{'name':'Alex Sample','gender':''},'status':'submitted','consent':True})
    assert r.status_code==200
    call(client,'logout','POST',{});login(client)
    assert call(client,'intake').json['data']['gender']==''

def test_submission_ack_required(client):
    login(client);assert call(client,'intake','PUT',{'data':{'name':'Alex'},'status':'submitted','consent':False}).status_code==400

def test_future_birthdate_rejected(client):
    login(client);assert call(client,'intake','PUT',{'data':{'dob':str(date.today()+timedelta(days=1))},'status':'draft'}).status_code==400

def test_patient_cannot_list_or_access_other_patients(client):
    login(client);assert call(client,'patients').status_code==403;assert call(client,'patients/1').status_code==403

def test_other_doctor_access_denied(client):
    login(client,'doctor',2)
    assert call(client,'patients/41').status_code==403
    assert call(client,'notes?patient=41').status_code==403
    assert call(client,'messages?patient=41').status_code==403
    assert call(client,'notes?patient=abc').status_code==400

def test_assigned_doctor_can_read(client):
    login(client,'doctor');r=call(client,'patients');assert r.status_code==200
    patient=next(p for p in r.json['patients'] if p['email']=='patient@example.com')
    r=call(client,'patients/'+str(patient['id']));assert r.status_code==200

def test_publish_and_patient_history(client):
    login(client,'doctor');pid=next(p['id'] for p in call(client,'patients').json['patients'] if p['email']=='patient@example.com')
    before=len(call(client,f'notes?patient={pid}').json['notes'])
    r=call(client,f'notes?patient={pid}','POST',{'title':'Second sample visit','visit_date':str(date.today()),'assessment':'Sample review','suggestions':'Saved sample suggestions','prescription':'No medication prescribed. Sample only.','meridians':['LU','ST']})
    assert r.status_code==200
    call(client,'logout','POST',{});login(client)
    r=call(client,'notes');assert len(r.json['notes'])==before+1 and r.json['notes'][0]['title']=='Second sample visit'
    assert call(client,'notes','POST',{'title':'Fake'}).status_code==403

def test_messages_are_saved_and_scoped(client):
    login(client);assert call(client,'messages','POST',{'text':'Sample follow-up question'}).status_code==200
    call(client,'logout','POST',{});login(client,'doctor')
    pid=next(p['id'] for p in call(client,'patients').json['patients'] if p['email']=='patient@example.com')
    assert call(client,f'messages?patient={pid}').json['messages'][-1]['text']=='Sample follow-up question'
    call(client,f'messages?patient={pid}','POST',{'text':'Saved sample reply'})
    call(client,'logout','POST',{});login(client)
    assert call(client,'messages').json['messages'][-1]['sender']=='doctor'

def test_appointment_lifecycle_and_collision(client):
    login(client);data={'day':str(date.today()+timedelta(days=5)),'time':'10:30','service':'Care discussion'}
    assert call(client,'appointments','POST',data).status_code==200
    assert call(client,'appointments','POST',data).status_code==409
    aid=call(client,'appointments').json['appointments'][-1]['id']
    assert call(client,f'appointments/{aid}','PATCH',{'status':'confirmed'}).status_code==403
    call(client,'logout','POST',{});login(client,'doctor',2)
    assert call(client,f'appointments/{aid}','PATCH',{'status':'confirmed'}).status_code==404
    call(client,'logout','POST',{});login(client,'doctor')
    assert call(client,f'appointments/{aid}','PATCH',{'status':'completed'}).status_code==400
    assert call(client,f'appointments/{aid}','PATCH',{'status':'confirmed'}).status_code==200
    assert call(client,f'appointments/{aid}','PATCH',{'status':'completed'}).status_code==200

def test_past_appointment_rejected(client):
    login(client);r=call(client,'appointments','POST',{'day':'2000-01-01','time':'09:00','service':'Initial consultation'});assert r.status_code==400

def test_pending_doctor_not_auto_approved(client):
    r=call(client,'doctor-application','POST',{'name':'Pending Sample','email':'pending@example.com','card':'TEST-999','specialty':'General','evidence':'Fictional application'})
    assert r.status_code==200
    assert call(client,'login','POST',{'email':'pending@example.com','card':'TEST-999','password':'DemoCare!2026','role':'doctor'}).status_code==401

def test_export_own_records(client):
    login(client);r=call(client,'export');assert r.status_code==200
    assert {'account','intake','notes','messages','appointments'}<=r.json.keys()
    assert 'password' not in r.json['account']

def test_payloads_encrypted_and_audited(app):
    con=sqlite3.connect(app.config['DATABASE'])
    assert con.execute('SELECT COUNT(*) FROM audit').fetchone()[0]>0
    for table in ['intakes','notes','messages']:
        rows=con.execute(f'SELECT payload FROM {table}').fetchall(); assert rows
        for (payload,) in rows:
            assert payload.startswith('gAAAA') and 'Sample' not in payload
    con.close()

def test_headers_and_logout(client):
    login(client);r=call(client,'notes');assert r.headers['Cache-Control']=='no-store'
    assert r.headers['X-Frame-Options']=='DENY'
    call(client,'logout','POST',{});assert call(client,'notes').status_code==401

def test_invalid_json_rejected(client):
    login(client);assert call(client,'messages','POST',[]).status_code==400

def test_password_change(client):
    call(client,'register','POST',{'name':'Password Test','email':'password-test@example.com','password':'InitialPassword!2026','consent':True})
    assert call(client,'password','POST',{'current':'wrong','new':'ChangedPassword!2026'}).status_code==403
    assert call(client,'password','POST',{'current':'InitialPassword!2026','new':'ChangedPassword!2026'}).status_code==200
    call(client,'logout','POST',{})
    assert call(client,'login','POST',{'email':'password-test@example.com','password':'ChangedPassword!2026','role':'patient'}).status_code==200
