from flask import Blueprint, render_template, request, redirect, url_for, flash, session, current_app, send_file, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from functools import wraps
from pathlib import Path
from datetime import date, timedelta, datetime
import pytz
from datetime import datetime
import pandas as pd, csv, io, json, sqlite3
from .db import get_db
from .ml import train_models, load_model, predict_probability, FEATURES
import time, math, calendar

bp=Blueprint('main',__name__)
def admin_required(fn):
    @wraps(fn)
    def wrapped(*a, **kw):
        if not session.get('user_id'):
            flash('Please sign in to continue.', 'warning'); return redirect(url_for('main.login'))
        if session.get('role') != 'Admin':
            flash('Administrator access is required for this action.', 'danger')
            return redirect(url_for('main.dashboard'))
        return fn(*a, **kw)
    return wrapped

def login_required(fn):
    @wraps(fn)
    def wrapped(*a,**kw):
        if not session.get('user_id'): flash('Please sign in to continue.','warning'); return redirect(url_for('main.login'))
        return fn(*a,**kw)
    return wrapped
def get_metrics():
    db=get_db(); total=db.execute('SELECT COUNT(*) n FROM employees').fetchone()['n']; attr=db.execute("SELECT COUNT(*) n FROM employees WHERE lower(attrition)='yes'").fetchone()['n']
    avg=db.execute('SELECT AVG(salary) n FROM employees').fetchone()['n'] or 0
    return {'total':total,'attrition':attr,'rate':round(attr/total*100,1) if total else 0,'avg_salary':round(avg,0)}
def get_attrition_trends(db, selected_year=None):
    """Return recorded exit trends for a selected calendar year; never infer exit dates."""
    yearly = [dict(r) for r in db.execute("""SELECT substr(attrition_date,1,4) label, COUNT(*) count
        FROM employees WHERE lower(attrition)='yes' AND attrition_date IS NOT NULL
        AND length(attrition_date)>=7 GROUP BY substr(attrition_date,1,4) ORDER BY label""").fetchall()]
    available_years = [str(row['label']) for row in yearly]
    latest_year = yearly[-1]['label'] if yearly else str(date.today().year)
    trend_year = str(selected_year) if selected_year and str(selected_year) in available_years else latest_year
    monthly_rows = db.execute("""SELECT substr(attrition_date,6,2) month, COUNT(*) count
        FROM employees WHERE lower(attrition)='yes' AND substr(attrition_date,1,4)=?
        AND attrition_date IS NOT NULL GROUP BY substr(attrition_date,6,2)""", (trend_year,)).fetchall()
    monthly_map = {int(r['month']): int(r['count']) for r in monthly_rows if r['month'].isdigit()}
    months = [{'label': calendar.month_abbr[m], 'count': monthly_map.get(m, 0)} for m in range(1,13)]
    total_employees = db.execute('SELECT COUNT(*) FROM employees').fetchone()[0]
    for row in yearly:
        row['rate'] = round((row['count'] / total_employees) * 100, 2) if total_employees else 0
    selected_count = next((int(row['count']) for row in yearly if str(row['label']) == trend_year), 0)
    selected_rate = round((selected_count / total_employees) * 100, 2) if total_employees else 0
    return months, yearly, trend_year, available_years, selected_rate

@bp.route('/')
def home(): return redirect(url_for('main.dashboard') if session.get('user_id') else url_for('main.login'))
@bp.route('/login',methods=['GET','POST'])
def login():
    if request.method=='POST':
        db=get_db(); username=request.form.get('username','').strip(); client=request.remote_addr or 'unknown'; key=f'{client}|{username.lower()}'
        db.execute('CREATE TABLE IF NOT EXISTS login_attempts (attempt_key TEXT PRIMARY KEY, failures INTEGER NOT NULL DEFAULT 0, window_start REAL NOT NULL, blocked_until REAL NOT NULL DEFAULT 0)')
        now=time.time(); rec=db.execute('SELECT * FROM login_attempts WHERE attempt_key=?',(key,)).fetchone()
        if rec and rec['blocked_until'] > now:
            flash(f'Too many failed attempts. Try again in {max(1, math.ceil(rec["blocked_until"]-now))} seconds.','danger'); return render_template('login.html'), 429
        u=db.execute('SELECT * FROM users WHERE username=?',(username,)).fetchone()
        if u and check_password_hash(u['password_hash'],request.form.get('password','')):
            db.execute('DELETE FROM login_attempts WHERE attempt_key=?',(key,)); db.commit(); session.clear(); session['user_id']=u['user_id']; session['username']=u['username']; session['role']=u['role']; return redirect(url_for('main.dashboard'))
        if rec and now-rec['window_start'] < 900: failures=rec['failures']+1; window=rec['window_start']
        else: failures=1; window=now
        blocked=now+900 if failures>=5 else 0
        db.execute('INSERT INTO login_attempts(attempt_key,failures,window_start,blocked_until) VALUES(?,?,?,?) ON CONFLICT(attempt_key) DO UPDATE SET failures=excluded.failures,window_start=excluded.window_start,blocked_until=excluded.blocked_until',(key,failures,window,blocked)); db.commit()
        flash('Invalid username or password.','danger')
    return render_template('login.html')
@bp.route('/register',methods=['GET','POST'])
def register():
    if request.method=='POST':
        username=request.form.get('username','').strip(); password=request.form.get('password','')
        if len(username)<3 or len(password)<8: flash('Username must be 3+ characters and password at least 8 characters.','danger')
        else:
            try:
                db=get_db(); role='Admin' if db.execute('SELECT COUNT(*) FROM users').fetchone()[0] == 0 else 'HR'; db.execute('INSERT INTO users(username,password_hash,role) VALUES(?,?,?)',(username,generate_password_hash(password),role)); db.commit(); flash(f'Account created with {role} role. Please sign in.','success'); return redirect(url_for('main.login'))
            except sqlite3.IntegrityError: flash('That username is already taken.','danger')
    return render_template('register.html')
@bp.route('/logout', methods=['POST'])
def logout(): session.clear(); return redirect(url_for('main.login'))
@bp.route('/dashboard')
@login_required
def dashboard():
    db=get_db(); metrics=get_metrics()
    dept=db.execute("SELECT department,COUNT(*) total,SUM(CASE WHEN lower(attrition)='yes' THEN 1 ELSE 0 END) attrited,ROUND(AVG(salary),0) avg_salary FROM employees GROUP BY department ORDER BY total DESC").fetchall()
    latest=db.execute('SELECT * FROM employees ORDER BY employee_id DESC LIMIT 8').fetchall()
    monthly_attrition, yearly_attrition, trend_year, trend_years, selected_year_rate = get_attrition_trends(db, request.args.get('year'))
    # Use India Standard Time explicitly so greetings do not depend on the computer's timezone.
    current_hour = datetime.now(
    pytz.timezone("Asia/Kolkata")
).hour
    if 5 <= current_hour < 12:
        greeting = 'Good morning'
    elif 12 <= current_hour < 17:
        greeting = 'Good afternoon'
    elif 17 <= current_hour < 21:
        greeting = 'Good evening'
    else:
        greeting = 'Good night'
    return render_template('dashboard.html',metrics=metrics,departments=[dict(x) for x in dept],latest=latest,greeting=greeting,monthly_attrition=monthly_attrition,yearly_attrition=yearly_attrition,trend_year=trend_year,trend_years=trend_years,selected_year_rate=selected_year_rate,has_exit_dates=bool(yearly_attrition))
@bp.route('/employees')
@login_required
def employees():
    db=get_db(); q=request.args.get('q','').strip(); dep=request.args.get('department','')
    sql='SELECT * FROM employees WHERE (name LIKE ? OR employee_code LIKE ? OR designation LIKE ?)'; args=[f'%{q}%',f'%{q}%',f'%{q}%']
    if dep: sql+=' AND department=?'; args.append(dep)
    sql+=' ORDER BY employee_id DESC LIMIT 1000'; data=db.execute(sql,args).fetchall(); departments=[r['department'] for r in db.execute('SELECT DISTINCT department FROM employees ORDER BY department')]
    return render_template('employees.html',employees=data,q=q,departments=departments,selected=dep)
@bp.route('/employees/new',methods=['GET','POST'])
@bp.route('/employees/<int:employee_id>/edit',methods=['GET','POST'])
@login_required
def employee_form(employee_id=None):
    db=get_db(); item=db.execute('SELECT * FROM employees WHERE employee_id=?',(employee_id,)).fetchone() if employee_id else None
    if employee_id and not item: flash('Employee not found.','danger'); return redirect(url_for('main.employees'))
    if request.method=='POST':
        f=request.form; code=f.get('employee_code','').strip(); name=f.get('name','').strip()
        try:
            values=(code,name,f.get('department','').strip(),f.get('designation','').strip(),f.get('joining_date') or date.today().isoformat(),float(f.get('salary') or 0),int(f.get('age') or 0),f.get('gender',''),f.get('marital_status',''),int(f.get('job_satisfaction') or 3),int(f.get('work_life_balance') or 3),f.get('overtime','No'),float(f.get('years_at_company') or 0),float(f.get('years_since_promotion') or 0),float(f.get('training_hours') or 0),float(f.get('performance_rating') or 3),int(f.get('absent_days') or 0),f.get('attrition','No'))
            if not code or not name or not values[2] or not values[3]: raise ValueError('Employee code, name, department and designation are required.')
            if employee_id: db.execute('''UPDATE employees SET employee_code=?,name=?,department=?,designation=?,joining_date=?,salary=?,age=?,gender=?,marital_status=?,job_satisfaction=?,work_life_balance=?,overtime=?,years_at_company=?,years_since_promotion=?,training_hours=?,performance_rating=?,absent_days=?,attrition=? WHERE employee_id=?''',values+(employee_id,))
            else: db.execute('''INSERT INTO employees(employee_code,name,department,designation,joining_date,salary,age,gender,marital_status,job_satisfaction,work_life_balance,overtime,years_at_company,years_since_promotion,training_hours,performance_rating,absent_days,attrition) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',values)
            db.commit(); flash('Employee saved successfully.','success'); return redirect(url_for('main.employees'))
        except sqlite3.IntegrityError: flash('Employee code must be unique.','danger')
        except (ValueError,TypeError) as e: flash(str(e) or 'Please check the form values.','danger')
    return render_template('employee_form.html',item=item)
@bp.route('/employees/<int:employee_id>/delete',methods=['POST'])
@admin_required
def employee_delete(employee_id):
    db=get_db(); db.execute('DELETE FROM employees WHERE employee_id=?',(employee_id,)); db.commit(); flash('Employee deleted.','success'); return redirect(url_for('main.employees'))
@bp.route('/upload',methods=['GET','POST'])
@admin_required
def upload():
    if request.method == 'POST':
        file = request.files.get('dataset')
        if not file or not file.filename.lower().endswith('.csv'):
            flash('Upload a CSV file only.', 'danger'); return redirect(url_for('main.upload'))
        required = {'EmployeeNumber','Age','Department','JobRole','MonthlyIncome','JobSatisfaction','WorkLifeBalance','OverTime','YearsAtCompany','YearsSinceLastPromotion','TrainingTimesLastYear','PerformanceRating','AbsentDaysLastYear','Attrition'}
        numeric_ranges = {'EmployeeNumber':(1,None),'Age':(16,100),'MonthlyIncome':(0,None),'JobSatisfaction':(1,4),'WorkLifeBalance':(1,4),'YearsAtCompany':(0,100),'YearsSinceLastPromotion':(0,100),'TrainingTimesLastYear':(0,100),'PerformanceRating':(1,5),'AbsentDaysLastYear':(0,366)}
        try:
            raw = file.stream.read()
            if len(raw) > current_app.config['MAX_CONTENT_LENGTH']: raise ValueError('File exceeds the 8 MB upload limit.')
            try: df = pd.read_csv(io.BytesIO(raw), keep_default_na=False)
            except Exception as exc: raise ValueError(f'CSV could not be parsed: {exc}')
            missing = required - set(df.columns)
            if missing: raise ValueError('Missing required columns: ' + ', '.join(sorted(missing)))
            if df.empty: raise ValueError('The CSV has a header but no employee rows.')
            errors=[]; seen=set()
            for idx, row in df.iterrows():
                line=idx+2; code=str(row['EmployeeNumber']).strip()
                if not code: errors.append(f'Row {line}: EmployeeNumber is required.')
                else:
                    try:
                        code_num=int(code)
                        if code_num <= 0: raise ValueError()
                        normalized=str(code_num).zfill(4)
                        if normalized in seen: errors.append(f'Row {line}: duplicate EmployeeNumber {code}.')
                        seen.add(normalized)
                    except (ValueError,OverflowError): errors.append(f'Row {line}: EmployeeNumber must be a positive whole number.')
                for col in ['Department','JobRole','OverTime','Attrition']:
                    if not str(row[col]).strip(): errors.append(f'Row {line}: {col} cannot be blank.')
                if str(row['OverTime']).strip().lower() not in {'yes','no'}: errors.append(f'Row {line}: OverTime must be Yes or No.')
                if str(row['Attrition']).strip().lower() not in {'yes','no'}: errors.append(f'Row {line}: Attrition must be Yes or No.')
                for col,(lo,hi) in numeric_ranges.items():
                    try:
                        val=float(row[col])
                        if not math.isfinite(val) or (col in {'EmployeeNumber','Age','JobSatisfaction','WorkLifeBalance','PerformanceRating','AbsentDaysLastYear'} and not val.is_integer()): raise ValueError()
                        if val < lo or (hi is not None and val > hi): raise ValueError()
                    except (ValueError,TypeError): errors.append(f'Row {line}: {col} must be a valid number in range {lo} to {hi if hi is not None else "∞"}.')
            if errors:
                msg = 'CSV rejected: found validation errors. No records were imported. ' + ' '.join(errors[:20])
                if len(errors)>20: msg += f' Plus {len(errors)-20} more error(s).'
                flash(msg, 'danger'); return redirect(url_for('main.upload'))
            db=get_db(); db.execute('BEGIN')
            for _,r in df.iterrows():
                empcode=str(int(float(r['EmployeeNumber']))).zfill(4)
                years=float(r['YearsAtCompany']); joining=(date.today()-timedelta(days=int(years*365))).isoformat()
                exit_date = str(r.get('AttritionDate', '')).strip() or None
                if exit_date and (pd.isna(pd.to_datetime(exit_date, errors='coerce'))): raise ValueError(f'Invalid AttritionDate for employee {empcode}; use YYYY-MM-DD.')
                if exit_date: exit_date = pd.to_datetime(exit_date).date().isoformat()
                db.execute('''INSERT INTO employees(employee_code,name,department,designation,joining_date,salary,age,gender,marital_status,job_satisfaction,work_life_balance,overtime,years_at_company,years_since_promotion,training_hours,performance_rating,absent_days,attrition,attrition_date) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(employee_code) DO UPDATE SET department=excluded.department,designation=excluded.designation,salary=excluded.salary,age=excluded.age,job_satisfaction=excluded.job_satisfaction,work_life_balance=excluded.work_life_balance,overtime=excluded.overtime,years_at_company=excluded.years_at_company,years_since_promotion=excluded.years_since_promotion,training_hours=excluded.training_hours,performance_rating=excluded.performance_rating,absent_days=excluded.absent_days,attrition=excluded.attrition,attrition_date=excluded.attrition_date''',(empcode,f'Employee {empcode}',str(r['Department']).strip(),str(r['JobRole']).strip(),joining,float(r['MonthlyIncome']),int(float(r['Age'])),str(r.get('Gender','')),str(r.get('MaritalStatus','')),int(float(r['JobSatisfaction'])),int(float(r['WorkLifeBalance'])),str(r['OverTime']).strip().title(),years,float(r['YearsSinceLastPromotion']),float(r['TrainingTimesLastYear']),float(r['PerformanceRating']),int(float(r['AbsentDaysLastYear'])),str(r['Attrition']).strip().title(),exit_date))
            db.commit(); flash(f'CSV validated successfully. {len(df)} employee row(s) imported or updated.', 'success'); return redirect(url_for('main.employees'))
        except ValueError as exc: flash(str(exc), 'danger')
        except Exception as exc:
            try: get_db().rollback()
            except Exception: pass
            flash(f'Import failed and changes were rolled back: {exc}', 'danger')
    return render_template('upload.html')

@bp.route('/records',methods=['GET','POST'])
@login_required
def records():
    db=get_db()
    # Provide clearly labelled illustrative records when an employee dataset exists,
    # so the page is useful immediately after upload. Never create records without employees.
    employee_rows = db.execute('SELECT * FROM employees ORDER BY name').fetchall()
    if employee_rows:
        if db.execute('SELECT COUNT(*) FROM attendance').fetchone()[0] == 0:
            today = date.today()
            for emp in employee_rows:
                absent = max(0, min(int(emp['absent_days'] or 0), 8))
                for offset in (2, 1, 0):
                    year = today.year
                    month_num = today.month - offset
                    while month_num <= 0:
                        month_num += 12; year -= 1
                    month_value = f'{year:04d}-{month_num:02d}'
                    days_in_month = calendar.monthrange(year, month_num)[1]
                    workdays = min(22, days_in_month)
                    leave_days = min(absent // 3, max(0, workdays - 1))
                    present_days = max(0, workdays - leave_days)
                    db.execute("INSERT OR IGNORE INTO attendance(employee_id,month,present_days,leave_days,record_source) VALUES(?,?,?,?, 'demo')", (emp['employee_id'], month_value, present_days, leave_days))
        if db.execute('SELECT COUNT(*) FROM performance').fetchone()[0] == 0:
            for emp in employee_rows:
                rating = max(1.0, min(5.0, float(emp['performance_rating'] or 3)))
                training = max(0.0, float(emp['training_hours'] or 0))
                db.execute("INSERT INTO performance(employee_id,rating,training_hours,appraisal_score,review_date,record_source) VALUES(?,?,?,?,?,'demo')", (emp['employee_id'], rating, training, rating, date.today().isoformat()))
        db.commit()
    employees=db.execute('SELECT employee_id,employee_code,name FROM employees ORDER BY name').fetchall()
    if request.method=='POST':
        try:
            employee_id=int(request.form.get('employee_id')); kind=request.form.get('record_type')
            if not db.execute('SELECT 1 FROM employees WHERE employee_id=?',(employee_id,)).fetchone(): raise ValueError('Choose a valid employee.')
            if kind=='attendance':
                month=request.form.get('month','').strip(); present=int(request.form.get('present_days') or 0); leave=int(request.form.get('leave_days') or 0)
                try:
                    month_date = datetime.strptime(month, '%Y-%m').date()
                    days_in_month = calendar.monthrange(month_date.year, month_date.month)[1]
                except (ValueError, TypeError):
                    raise ValueError('Choose a valid attendance month.')
                if present<0 or leave<0 or present+leave>days_in_month: raise ValueError(f'Present and leave days combined cannot exceed {days_in_month} for this month.')
                db.execute("INSERT INTO attendance(employee_id,month,present_days,leave_days,record_source) VALUES(?,?,?,?,?) ON CONFLICT(employee_id,month) DO UPDATE SET present_days=excluded.present_days,leave_days=excluded.leave_days,record_source='manual'",(employee_id,month,present,leave,'manual'))
                flash('Attendance record saved.','success')
            elif kind=='performance':
                rating=float(request.form.get('rating') or 3); training=float(request.form.get('training_hours') or 0); appraisal=float(request.form.get('appraisal_score') or 3); review=request.form.get('review_date') or date.today().isoformat()
                if not 1<=rating<=5 or not 1<=appraisal<=5 or training<0: raise ValueError('Ratings must be 1–5 and training hours cannot be negative.')
                try: datetime.strptime(review, '%Y-%m-%d')
                except ValueError: raise ValueError('Choose a valid review date.')
                db.execute("INSERT INTO performance(employee_id,rating,training_hours,appraisal_score,review_date,record_source) VALUES(?,?,?,?,?,?)",(employee_id,rating,training,appraisal,review,'manual')); flash('Performance review saved.','success')
            else: raise ValueError('Choose a record type.')
            db.commit(); return redirect(url_for('main.records'))
        except (ValueError,TypeError) as e: flash(str(e) or 'Check the values and try again.','danger')
    attendance=db.execute('SELECT a.*,e.name,e.employee_code FROM attendance a JOIN employees e ON a.employee_id=e.employee_id ORDER BY a.month DESC,a.attendance_id DESC LIMIT 100').fetchall()
    performance=db.execute('SELECT p.*,e.name,e.employee_code FROM performance p JOIN employees e ON p.employee_id=e.employee_id ORDER BY p.review_date DESC,p.performance_id DESC LIMIT 100').fetchall()
    return render_template('records.html',employees=employees,attendance=attendance,performance=performance,today=date.today().isoformat(),month=date.today().strftime('%Y-%m'))

@bp.route('/dataset/download')
@login_required
def dataset_download():
    return send_file(current_app.config['DATASET'],as_attachment=True,download_name='hr_attrition_dataset.csv',mimetype='text/csv')

@bp.route('/analytics')
@login_required
def analytics():
    db=get_db()
    start=request.args.get('start_date','').strip(); end=request.args.get('end_date','').strip(); department=request.args.get('department','').strip()
    for value,label in ((start,'start date'),(end,'end date')):
        if value:
            try: datetime.strptime(value,'%Y-%m-%d')
            except ValueError: flash(f'Invalid {label}; use YYYY-MM-DD.', 'danger'); return redirect(url_for('main.analytics'))
    if start and end and start>end: flash('Start date must be on or before end date.', 'danger'); return redirect(url_for('main.analytics'))
    where=[]; args=[]
    if start: where.append('joining_date >= ?'); args.append(start)
    if end: where.append('joining_date <= ?'); args.append(end)
    if department: where.append('department = ?'); args.append(department)
    clause=(' WHERE '+' AND '.join(where)) if where else ''
    dept=[dict(x) for x in db.execute(f"SELECT department,COUNT(*) total,SUM(CASE WHEN lower(attrition)='yes' THEN 1 ELSE 0 END) attrited,ROUND(AVG(salary),0) avg_salary,ROUND(AVG(years_at_company),1) avg_tenure FROM employees{clause} GROUP BY department ORDER BY total DESC",args).fetchall()]
    tenure=[dict(x) for x in db.execute(f"SELECT CASE WHEN years_at_company<2 THEN '0–1 years' WHEN years_at_company<5 THEN '2–4 years' WHEN years_at_company<10 THEN '5–9 years' ELSE '10+ years' END tenure_band,COUNT(*) total,SUM(CASE WHEN lower(attrition)='yes' THEN 1 ELSE 0 END) attrited FROM employees{clause} GROUP BY tenure_band",args).fetchall()]
    risk=db.execute(f"SELECT * FROM employees{clause}{' AND' if clause else ' WHERE'} lower(attrition)='yes' ORDER BY job_satisfaction ASC, overtime DESC LIMIT 20",args).fetchall()
    departments=[r['department'] for r in db.execute('SELECT DISTINCT department FROM employees ORDER BY department')]
    return render_template('analytics.html',departments=dept,tenure=tenure,highrisk=risk,department_options=departments,selected_department=department,start_date=start,end_date=end)

@bp.route('/analytics/export.csv')
@login_required
def analytics_export():
    start=request.args.get('start_date','').strip(); end=request.args.get('end_date','').strip(); department=request.args.get('department','').strip()
    where=[]; args=[]
    if start: where.append('joining_date >= ?'); args.append(start)
    if end: where.append('joining_date <= ?'); args.append(end)
    if department: where.append('department = ?'); args.append(department)
    clause=(' WHERE '+' AND '.join(where)) if where else ''
    rows=get_db().execute(f"SELECT department,COUNT(*) total,SUM(CASE WHEN lower(attrition)='yes' THEN 1 ELSE 0 END) attrited,ROUND(100.0*SUM(CASE WHEN lower(attrition)='yes' THEN 1 ELSE 0 END)/NULLIF(COUNT(*),0),2) attrition_rate,ROUND(AVG(salary),2) avg_monthly_salary,ROUND(AVG(years_at_company),2) avg_tenure FROM employees{clause} GROUP BY department ORDER BY department",args).fetchall()
    out=io.StringIO(); writer=csv.writer(out); writer.writerow(['Department','Headcount','Recorded attrition count','Recorded attrition rate %','Average monthly salary','Average tenure years'])
    for row in rows: writer.writerow(list(row))
    from flask import Response
    return Response(out.getvalue(),mimetype='text/csv',headers={'Content-Disposition':'attachment; filename=department_attrition_analytics.csv'})

@bp.route('/prediction',methods=['GET','POST'])
@login_required
def prediction():
    result=None; bundle=load_model(Path(current_app.root_path).parent/'models'); employees=get_db().execute('SELECT employee_id,employee_code,name FROM employees ORDER BY name').fetchall()
    if request.method=='POST':
        try:
            if not bundle: raise ValueError('Train a model first using the Train model button.')
            db=get_db(); mode=request.form.get('mode','employee')
            if mode=='employee':
                emp=db.execute('SELECT * FROM employees WHERE employee_id=?',(request.form.get('employee_id'),)).fetchone()
                if not emp: raise ValueError('Choose a valid employee.')
                row={'Age':emp['age'],'Department':emp['department'],'JobRole':emp['designation'],'MonthlyIncome':emp['salary'],'JobSatisfaction':emp['job_satisfaction'],'WorkLifeBalance':emp['work_life_balance'],'OverTime':emp['overtime'],'YearsAtCompany':emp['years_at_company'],'YearsSinceLastPromotion':emp['years_since_promotion'],'TrainingTimesLastYear':emp['training_hours'],'PerformanceRating':emp['performance_rating'],'AbsentDaysLastYear':emp['absent_days'],'Gender':emp['gender'] or 'Unknown','MaritalStatus':emp['marital_status'] or 'Unknown'}; empid=emp['employee_id']; empname=emp['name']
            else:
                row={k:request.form.get(k) for k in FEATURES};
                for k in ['Age','MonthlyIncome','JobSatisfaction','WorkLifeBalance','YearsAtCompany','YearsSinceLastPromotion','TrainingTimesLastYear','PerformanceRating','AbsentDaysLastYear']: row[k]=float(row[k])
                empid=None; empname='Manual assessment'
            p=predict_probability(bundle,row); level='High' if p>=.65 else ('Medium' if p>=.35 else 'Low')
            db.execute('INSERT INTO attrition_predictions(employee_id,probability,risk_level,model_name) VALUES(?,?,?,?)',(empid,p,level,bundle['name'])); db.commit()
            result={'name':empname,'probability':round(p*100,1),'risk':level,'model':bundle['name']}
        except Exception as e: flash(str(e),'danger')
    history=get_db().execute('SELECT p.*,e.name,e.employee_code FROM attrition_predictions p LEFT JOIN employees e ON p.employee_id=e.employee_id ORDER BY predicted_at DESC LIMIT 30').fetchall()
    return render_template('prediction.html',employees=employees,result=result,history=history,trained=bool(bundle))
@bp.route('/train',methods=['POST'])
@admin_required
def train():
    path=Path(current_app.root_path).parent/'models'
    try:
        results,n,yes,no=train_models(current_app.config['DATASET'],path); session['model_results']=results; session['train_info']={'rows':n,'attrited':yes,'retained':no,'imbalance_ratio':round(max(yes,no)/max(1,min(yes,no)),2)}; flash('Model training and evaluation completed. Best model saved.','success')
    except Exception as e: flash(f'Model training failed: {e}','danger')
    return redirect(url_for('main.reports'))
@bp.route('/reports')
@login_required
def reports():
    metrics=get_metrics(); results=session.get('model_results',[]); info=session.get('train_info',{})
    return render_template('reports.html',metrics=metrics,results=results,info=info)
@bp.route('/reports/download')
@login_required
def report_download():
    db=get_db(); rows=db.execute('SELECT employee_code,name,department,designation,joining_date,salary,years_at_company,job_satisfaction,overtime,performance_rating,attrition FROM employees ORDER BY department,name').fetchall()
    out=io.StringIO(); writer=csv.writer(out); writer.writerow(rows[0].keys() if rows else ['employee_code','name','department','designation','joining_date','salary','years_at_company','job_satisfaction','overtime','performance_rating','attrition'])
    for r in rows: writer.writerow(list(r))
    from flask import Response
    return Response(out.getvalue(),mimetype='text/csv',headers={'Content-Disposition':'attachment; filename=employee_attrition_report.csv'})
@bp.route('/api/dashboard')
@login_required
def dashboard_api():
    db=get_db(); return jsonify({'metrics':get_metrics(),'departments':[dict(x) for x in db.execute("SELECT department,COUNT(*) total,SUM(CASE WHEN lower(attrition)='yes' THEN 1 ELSE 0 END) attrited FROM employees GROUP BY department").fetchall()]})
