"""Acupuncture care portal. Sample data only until independently reviewed."""
import os,json,sqlite3,secrets,time,re,sys
from pathlib import Path
from functools import wraps
from datetime import datetime,timedelta,date
from flask import Flask,request,jsonify,session,g,send_from_directory
from werkzeug.security import generate_password_hash,check_password_hash
from cryptography.fernet import Fernet,InvalidToken

ROOT=Path(__file__).parent

def create_app(test_config=None):
    app=Flask(__name__,static_folder='static')
    data=Path(os.environ.get('DATA_DIR',str(ROOT/'data'))); data.mkdir(parents=True,exist_ok=True)
    def persistent(name,generate):
        f=data/name
        if not f.exists():
            try:
                fd=os.open(str(f),os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
                with os.fdopen(fd,'w') as out: out.write(generate())
            except FileExistsError: pass
        return f.read_text().strip()
    app.config.update(SECRET_KEY=os.environ.get('SECRET_KEY') or persistent('session.key',lambda:secrets.token_hex(32)),DATABASE=str(data/'care.sqlite3'),DEMO_MODE=os.environ.get('DEMO_MODE','1')=='1',SESSION_COOKIE_HTTPONLY=True,SESSION_COOKIE_SAMESITE='Lax',SESSION_COOKIE_SECURE=os.environ.get('COOKIE_SECURE')=='1',PERMANENT_SESSION_LIFETIME=timedelta(minutes=30),MAX_CONTENT_LENGTH=500_000)
    if test_config: app.config.update(test_config)
    cipher=Fernet(os.environ.get('DATA_KEY') or persistent('records.key',lambda:Fernet.generate_key().decode()))
    def enc(x): return cipher.encrypt(json.dumps(x,ensure_ascii=False).encode()).decode()
    def dec(x): return json.loads(cipher.decrypt(x.encode())) if x else {}
    def db():
        if 'db' not in g:
            g.db=sqlite3.connect(app.config['DATABASE'],timeout=15); g.db.row_factory=sqlite3.Row
            g.db.execute('PRAGMA foreign_keys=ON')
        return g.db
    @app.teardown_appcontext
    def close(_):
        if 'db' in g: g.pop('db').close()
    def now(): return datetime.now().astimezone().isoformat(timespec='seconds')
    with app.app_context():
        db().executescript('''
        CREATE TABLE IF NOT EXISTS doctors(id INTEGER PRIMARY KEY,name TEXT,email TEXT UNIQUE,card TEXT UNIQUE,specialty TEXT,bio TEXT,sample INTEGER DEFAULT 1);
        CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY,name TEXT NOT NULL,email TEXT UNIQUE NOT NULL,password TEXT NOT NULL,role TEXT DEFAULT 'patient',doctor_id INTEGER REFERENCES doctors(id),created TEXT);
        CREATE TABLE IF NOT EXISTS intakes(patient_id INTEGER PRIMARY KEY REFERENCES users(id),payload TEXT,status TEXT,updated TEXT);
        CREATE TABLE IF NOT EXISTS appointments(id INTEGER PRIMARY KEY,patient_id INTEGER REFERENCES users(id),doctor_id INTEGER REFERENCES doctors(id),day TEXT,time TEXT,service TEXT,status TEXT DEFAULT 'requested',created TEXT);
        CREATE UNIQUE INDEX IF NOT EXISTS reserved_slot ON appointments(doctor_id,day,time) WHERE status IN ('requested','confirmed');
        CREATE TABLE IF NOT EXISTS notes(id INTEGER PRIMARY KEY,patient_id INTEGER REFERENCES users(id),doctor_id INTEGER REFERENCES doctors(id),payload TEXT,created TEXT);
        CREATE TABLE IF NOT EXISTS messages(id INTEGER PRIMARY KEY,patient_id INTEGER REFERENCES users(id),doctor_id INTEGER REFERENCES doctors(id),sender TEXT,payload TEXT,created TEXT);
        CREATE TABLE IF NOT EXISTS applications(id INTEGER PRIMARY KEY,name TEXT,email TEXT UNIQUE,card TEXT,payload TEXT,status TEXT DEFAULT 'pending',created TEXT);
        CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY,actor INTEGER,action TEXT,target TEXT,created TEXT);
        CREATE TABLE IF NOT EXISTS attempts(key TEXT PRIMARY KEY,count INTEGER,until REAL);
        ''')
        doctors=json.loads((ROOT/'doctors.json').read_text())
        if app.config['DEMO_MODE']:
            for d in doctors:
                db().execute('INSERT OR IGNORE INTO doctors(id,name,email,card,specialty,bio) VALUES(?,?,?,?,?,?)',(d['id'],d['name'],d['email'],d['card'],d['specialty'],d['bio']))
                if not db().execute('SELECT 1 FROM users WHERE email=?',(d['email'],)).fetchone():
                    db().execute('INSERT INTO users(name,email,password,role,doctor_id,created) VALUES(?,?,?,?,?,?)',(d['name'],d['email'],generate_password_hash('DemoCare!2026'),'doctor',d['id'],now()))
            if not db().execute('SELECT 1 FROM users WHERE email=?',('patient@example.com',)).fetchone():
                cur=db().execute('INSERT INTO users(name,email,password,doctor_id,created) VALUES(?,?,?,?,?)',('Alex Sample','patient@example.com',generate_password_hash('DemoCare!2026'),1,now())); uid=cur.lastrowid
                db().execute('INSERT INTO intakes VALUES(?,?,?,?)',(uid,enc({'name':'Alex Sample','issue_1':'Sample shoulder discomfort','gender':''}),'draft',now()))
                db().execute('INSERT INTO notes(patient_id,doctor_id,payload,created) VALUES(?,?,?,?)',(uid,1,enc({'visit_date':date.today().isoformat(),'title':'Sample consultation record','assessment':'Fictional record used to demonstrate the care timeline. No diagnosis has been made.','suggestions':'Sample note only: discuss any new or persistent concern with a qualified clinician.','prescription':'No medication prescribed. Demonstration entry only.','treatment':'Sample consultation discussion; no treatment performed.','followup':'Arrange follow-up with your qualified clinician as appropriate.','meridians':['LU']}),now()))
        db().commit()
    class APIError(Exception):
        def __init__(self,message,status=400): self.message=message; self.status=status
    @app.errorhandler(APIError)
    def apierror(e):
        db().rollback(); return jsonify(error=e.message),e.status
    @app.errorhandler(413)
    def too_large(e): return jsonify(error='Request too large.'),413
    @app.errorhandler(404)
    def missing(e): return jsonify(error='Not found.'),404
    def body():
        x=request.get_json(silent=True)
        if not isinstance(x,dict): raise APIError('A JSON object is required.')
        return x
    def text(x,key,maxlen=6000,required=False):
        v=x.get(key,'')
        if not isinstance(v,str): raise APIError(f'Invalid {key}.')
        v=v.strip()
        if len(v)>maxlen or (required and not v): raise APIError(f'Check {key} (maximum {maxlen} characters).')
        return v
    def email(x):
        e=text(x,'email',254,True).lower()
        if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',e): raise APIError('Enter a valid email address.')
        return e
    def password(x,key='password'):
        p=text(x,key,128,True)
        if len(p)<12: raise APIError('Use a password of at least 12 characters.')
        return p
    def audit(action,target=''):
        db().execute('INSERT INTO audit(actor,action,target,created) VALUES(?,?,?,?)',(session.get('uid'),action,str(target),now()))
    def current():
        return db().execute('SELECT id,name,email,role,doctor_id FROM users WHERE id=?',(session.get('uid',-1),)).fetchone()
    def auth(role=None):
        def decorator(fn):
            @wraps(fn)
            def wrapped(*a,**kw):
                u=current()
                if not u: raise APIError('Please sign in.',401)
                if role and u['role']!=role: raise APIError('This action is not available for this account.',403)
                g.user=u
                return fn(*a,**kw)
            return wrapped
        return decorator
    def public(u):
        result=dict(u)
        result.pop('password',None); result.pop('created',None)
        d=db().execute('SELECT * FROM doctors WHERE id=?',(u['doctor_id'],)).fetchone()
        result['doctor']=dict(d) if d else None
        return result
    @app.before_request
    def security():
        if not request.path.startswith('/api/'): return
        session.permanent=True
        if 'csrf' not in session: session['csrf']=secrets.token_urlsafe(32)
        if request.method not in ('GET','HEAD','OPTIONS'):
            if not secrets.compare_digest(request.headers.get('X-CSRF-Token',''),session['csrf']): raise APIError('Session security token expired. Refresh the page.',403)
    @app.after_request
    def headers(r):
        r.headers['X-Content-Type-Options']='nosniff';r.headers['X-Frame-Options']='DENY'; r.headers['Referrer-Policy']='same-origin'
        r.headers['Content-Security-Policy']="default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; img-src 'self' data:; connect-src 'self'; media-src 'self' blob:; object-src 'none'; base-uri 'self'; frame-ancestors 'none'"
        if request.path.startswith('/api/'): r.headers['Cache-Control']='no-store'
        return r
    @app.get('/')
    def index(): return send_from_directory(ROOT/'static','index.html')
    @app.get('/api/bootstrap')
    def bootstrap():
        u=current(); return jsonify(csrf=session['csrf'],user=public(u) if u else None,demo=app.config['DEMO_MODE'])
    @app.get('/api/doctors')
    def directory(): return jsonify(doctors=[dict(d) for d in db().execute('SELECT * FROM doctors ORDER BY id')])
    @app.post('/api/register')
    def register():
        x=body(); name=text(x,'name',120,True); e=email(x); p=password(x)
        if x.get('consent') is not True: raise APIError('Please acknowledge the sample-data notice.')
        try:
            db().execute('BEGIN IMMEDIATE')
            d=db().execute("SELECT d.id,COUNT(u.id) n FROM doctors d LEFT JOIN users u ON u.doctor_id=d.id AND u.role='patient' GROUP BY d.id ORDER BY n,d.id LIMIT 1").fetchone()
            if not d: raise APIError('No approved practitioners are available. Contact the clinic.',503)
            cur=db().execute('INSERT INTO users(name,email,password,doctor_id,created) VALUES(?,?,?,?,?)',(name,e,generate_password_hash(p),d['id'],now()))
            uid=cur.lastrowid; session.clear();session.update(uid=uid,csrf=secrets.token_urlsafe(32));audit('register',uid);db().commit()
        except sqlite3.IntegrityError: raise APIError('An account already uses that email.',409)
        return jsonify(user=public(current()),csrf=session['csrf'])
    @app.post('/api/login')
    def login():
        x=body();e=email(x);p=text(x,'password',128,True);role=x.get('role','patient')
        key=request.remote_addr+':'+e; row=db().execute('SELECT * FROM attempts WHERE key=?',(key,)).fetchone()
        if row and row['until']>time.time() and row['count']>=8: raise APIError('Too many attempts. Try again in 15 minutes.',429)
        u=db().execute('SELECT * FROM users WHERE email=?',(e,)).fetchone()
        valid=u and check_password_hash(u['password'],p) and u['role']==role
        if role=='doctor': valid=valid and secrets.compare_digest(text(x,'card',100),db().execute('SELECT card FROM doctors WHERE id=?',(u['doctor_id'],)).fetchone()['card']) if u else False
        if not valid:
            count=row['count']+1 if row and row['until']>time.time() else 1
            db().execute('INSERT OR REPLACE INTO attempts VALUES(?,?,?)',(key,count,time.time()+900));db().commit()
            raise APIError('The email, password, role or doctor ID does not match.',401)
        db().execute('DELETE FROM attempts WHERE key=?',(key,));session.clear();session.update(uid=u['id'],csrf=secrets.token_urlsafe(32));audit('login',u['id']);db().commit()
        return jsonify(user=public(current()),csrf=session['csrf'])
    @app.post('/api/logout')
    def logout(): session.clear();return jsonify(ok=True)
    @app.post('/api/doctor-application')
    def apply():
        x=body();e=email(x);name=text(x,'name',120,True);card=text(x,'card',100,True)
        try: db().execute('INSERT INTO applications(name,email,card,payload,created) VALUES(?,?,?,?,?)',(name,e,card,enc({'specialty':text(x,'specialty',200),'evidence':text(x,'evidence',3000,True)}),now()));db().commit()
        except sqlite3.IntegrityError: raise APIError('An application for this email is already recorded.',409)
        return jsonify(ok=True,message='Application saved for manual verification. This does not grant doctor access.')
    @app.route('/api/intake',methods=['GET','PUT'])
    @auth('patient')
    def intake():
        uid=g.user['id']
        if request.method=='GET':
            r=db().execute('SELECT * FROM intakes WHERE patient_id=?',(uid,)).fetchone()
            return jsonify(data=dec(r['payload']) if r else {},status=r['status'] if r else 'not started',updated=r['updated'] if r else None)
        x=body(); value=x.get('data');status=x.get('status','draft')
        if not isinstance(value,dict) or len(json.dumps(value))>180000: raise APIError('Invalid intake data.')
        if status not in ('draft','submitted'): raise APIError('Invalid intake status.')
        # Gender and every reproductive-health field are intentionally optional.
        if status=='submitted' and (not str(value.get('name','')).strip() or not x.get('consent')): raise APIError('Name and submission acknowledgment are required. Gender is optional.')
        if value.get('dob'):
            try:
                if date.fromisoformat(value['dob'])>date.today(): raise ValueError()
            except (ValueError,TypeError): raise APIError('Check the date of birth.')
        stamp=now();db().execute('INSERT OR REPLACE INTO intakes VALUES(?,?,?,?)',(uid,enc(value),status,stamp));audit('save_intake',uid);db().commit()
        return jsonify(status=status,updated=stamp)
    def allowed_patient(pid):
        r=db().execute("SELECT id,name,email FROM users WHERE id=? AND role='patient' AND doctor_id=?",(pid,g.user['doctor_id'])).fetchone()
        if not r: raise APIError('Patient not available to this practitioner.',403)
        return r
    @app.get('/api/patients')
    @auth('doctor')
    def patients():
        return jsonify(patients=[dict(r) for r in db().execute("SELECT id,name,email FROM users WHERE doctor_id=? AND role='patient' ORDER BY name",(g.user['doctor_id'],))])
    @app.get('/api/patients/<int:pid>')
    @auth('doctor')
    def patient(pid):
        u=allowed_patient(pid);r=db().execute('SELECT * FROM intakes WHERE patient_id=?',(pid,)).fetchone();audit('read_patient',pid);db().commit()
        return jsonify(patient=dict(u),intake=dec(r['payload']) if r else {},status=r['status'] if r else 'not started')
    def patient_scope():
        if g.user['role']=='patient': return g.user['id']
        try: pid=int(request.args.get('patient','0'))
        except ValueError: raise APIError('Invalid patient.')
        allowed_patient(pid);return pid
    @app.route('/api/notes',methods=['GET','POST'])
    @auth()
    def notes():
        pid=patient_scope()
        if request.method=='GET':
            rows=db().execute('SELECT n.*,d.name doctor_name FROM notes n JOIN doctors d ON d.id=n.doctor_id WHERE patient_id=? ORDER BY n.id DESC',(pid,)).fetchall()
            audit('read_notes',pid);db().commit()
            return jsonify(notes=[{'id':r['id'],'doctor_name':r['doctor_name'],'created':r['created'],**dec(r['payload'])} for r in rows])
        if g.user['role']!='doctor': raise APIError('Only your assigned practitioner can publish care records.',403)
        x=body();v={k:text(x,k,6000,k in ('title','assessment','suggestions')) for k in ['title','assessment','suggestions','prescription','treatment','followup','visit_date']}
        try:
            if date.fromisoformat(v['visit_date'])>date.today(): raise ValueError()
        except ValueError: raise APIError('Enter a valid visit date that is not in the future.')
        keys=['LU','LI','ST','SP','HT','SI','BL','KI','PC','SJ','GB','LR','DU','RN'];m=x.get('meridians',[])
        if not isinstance(m,list) or any(c not in keys for c in m): raise APIError('Invalid meridian reference.')
        v['meridians']=m
        db().execute('INSERT INTO notes(patient_id,doctor_id,payload,created) VALUES(?,?,?,?)',(pid,g.user['doctor_id'],enc(v),now()));audit('publish_note',pid);db().commit();return jsonify(ok=True)
    @app.route('/api/messages',methods=['GET','POST'])
    @auth()
    def messages():
        pid=patient_scope()
        if request.method=='GET': return jsonify(messages=[{'id':r['id'],'sender':r['sender'],'text':dec(r['payload'])['text'],'created':r['created']} for r in db().execute('SELECT * FROM messages WHERE patient_id=? ORDER BY id',(pid,))])
        x=body();msg=text(x,'text',4000,True);did=g.user['doctor_id']
        db().execute('INSERT INTO messages(patient_id,doctor_id,sender,payload,created) VALUES(?,?,?,?,?)',(pid,did,g.user['role'],enc({'text':msg}),now()));audit('send_message',pid);db().commit();return jsonify(ok=True)
    @app.route('/api/appointments',methods=['GET','POST'])
    @auth()
    def appointments():
        u=g.user
        if request.method=='GET':
            field='a.patient_id' if u['role']=='patient' else 'a.doctor_id';v=u['id'] if u['role']=='patient' else u['doctor_id']
            rows=db().execute(f'SELECT a.*,u.name patient_name,d.name doctor_name FROM appointments a JOIN users u ON u.id=a.patient_id JOIN doctors d ON d.id=a.doctor_id WHERE {field}=? ORDER BY day,time',(v,)).fetchall()
            return jsonify(appointments=[dict(r) for r in rows])
        if u['role']!='patient': raise APIError('Only patients may request a time.',403)
        x=body();day=text(x,'day',10,True);slot=text(x,'time',5,True);service=text(x,'service',100,True)
        try:
            when=datetime.fromisoformat(day+'T'+slot)
            if when<=datetime.now(): raise ValueError()
        except ValueError: raise APIError('Choose a future date and time.')
        if slot not in ['09:00','10:30','12:00','14:00','15:30','17:00'] or service not in ['Initial consultation','Follow-up acupuncture','Care discussion']: raise APIError('Invalid consultation type or time slot.')
        try: db().execute('INSERT INTO appointments(patient_id,doctor_id,day,time,service,created) VALUES(?,?,?,?,?,?)',(u['id'],u['doctor_id'],day,slot,service,now()));audit('request_appointment',u['id']);db().commit()
        except sqlite3.IntegrityError: raise APIError('That slot is already requested. Choose another time.',409)
        return jsonify(ok=True)
    @app.patch('/api/appointments/<int:aid>')
    @auth()
    def update_appointment(aid):
        a=db().execute('SELECT * FROM appointments WHERE id=?',(aid,)).fetchone();u=g.user;status=body().get('status')
        if not a or (u['role']=='patient' and a['patient_id']!=u['id']) or (u['role']=='doctor' and a['doctor_id']!=u['doctor_id']): raise APIError('Appointment not found.',404)
        if a['status'] not in ('requested','confirmed'): raise APIError('This appointment is already closed.',409)
        if u['role']=='patient' and status!='cancelled': raise APIError('Patients can only cancel requests.',403)
        if status not in ('confirmed','cancelled','completed'): raise APIError('Invalid status.')
        if status=='completed' and a['status']!='confirmed': raise APIError('Confirm the visit before marking it completed.')
        db().execute('UPDATE appointments SET status=? WHERE id=?',(status,aid));audit('appointment_'+status,aid);db().commit();return jsonify(ok=True)
    @app.post('/api/password')
    @auth()
    def change_password():
        x=body();p=password(x,'new');row=db().execute('SELECT password FROM users WHERE id=?',(g.user['id'],)).fetchone()
        if not check_password_hash(row['password'],text(x,'current',128,True)): raise APIError('Current password does not match.',403)
        db().execute('UPDATE users SET password=? WHERE id=?',(generate_password_hash(p),g.user['id']));audit('change_password',g.user['id']);db().commit();return jsonify(ok=True)
    @app.get('/api/export')
    @auth('patient')
    def export():
        uid=g.user['id']; r=db().execute('SELECT * FROM intakes WHERE patient_id=?',(uid,)).fetchone()
        audit('export',uid);db().commit()
        return jsonify(account=public(g.user),intake=dec(r['payload']) if r else {},notes=[{'created':r['created'],**dec(r['payload'])} for r in db().execute('SELECT * FROM notes WHERE patient_id=?',(uid,))],messages=[{'created':r['created'],'sender':r['sender'],**dec(r['payload'])} for r in db().execute('SELECT * FROM messages WHERE patient_id=?',(uid,))],appointments=[dict(r) for r in db().execute('SELECT * FROM appointments WHERE patient_id=?',(uid,))])
    @app.cli.command('approve-doctor')
    def approve_doctor():
        import getpass
        e=input('Application email: ').strip().lower();a=db().execute("SELECT * FROM applications WHERE email=? AND status='pending'",(e,)).fetchone()
        if not a: print('No pending application.'); return
        print('Applicant:',a['name'],'ID:',a['card'],'evidence:',dec(a['payload']))
        if input('After independently verifying identity and licensing, type APPROVE: ')!='APPROVE': return
        p=getpass.getpass('Temporary password (12+ characters): ')
        if len(p)<12: print('Password too short.');return
        try:
            v=dec(a['payload']);cur=db().execute('INSERT INTO doctors(name,email,card,specialty,bio,sample) VALUES(?,?,?,?,?,0)',(a['name'],a['email'],a['card'],v['specialty'],'Clinic-approved practitioner'))
            db().execute('INSERT INTO users(name,email,password,role,doctor_id,created) VALUES(?,?,?,?,?,?)',(a['name'],e,generate_password_hash(p),'doctor',cur.lastrowid,now()))
            db().execute("UPDATE applications SET status='approved' WHERE id=?",(a['id'],));audit('approve_doctor',a['id']);db().commit();print('Approved. Send credentials through a secure independent channel.')
        except sqlite3.IntegrityError: db().rollback();print('Email or ID already exists. Approval cancelled.')
    return app

if __name__=='__main__':
    create_app().run(host=os.environ.get('HOST','127.0.0.1'),port=int(os.environ.get('PORT','8000')),debug=False)
