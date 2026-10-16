from pathlib import Path
import joblib
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split, StratifiedKFold, cross_validate
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score, confusion_matrix, roc_auc_score, brier_score_loss
from sklearn.linear_model import LogisticRegression
from sklearn.calibration import CalibratedClassifierCV

FEATURES = ['Age','Department','JobRole','MonthlyIncome','JobSatisfaction','WorkLifeBalance','OverTime','YearsAtCompany','YearsSinceLastPromotion','TrainingTimesLastYear','PerformanceRating','AbsentDaysLastYear','Gender','MaritalStatus']
TARGET='Attrition'

def train_models(csv_path, model_dir):
    df = pd.read_csv(csv_path)
    missing = set(FEATURES + [TARGET]) - set(df.columns)
    if missing:
        raise ValueError('Dataset is missing required ML columns: ' + ', '.join(sorted(missing)))
    df = df.dropna(subset=[TARGET]).copy()
    y = df[TARGET].astype(str).str.strip().str.title().map({'Yes': 1, 'No': 0})
    valid = y.notna(); X = df.loc[valid, FEATURES].copy(); y = y.loc[valid].astype(int)
    if len(y) < 20 or y.nunique() < 2:
        raise ValueError('Dataset needs at least 20 usable rows and both Attrition classes (Yes/No).')
    counts = y.value_counts().to_dict(); minority = min(counts.values())
    if minority < 3:
        raise ValueError(f'Not enough examples in the minority class for reliable cross-validation (class counts: retained={counts.get(0,0)}, attrited={counts.get(1,0)}). Add more records from the smaller class.')
    imbalance_ratio = round(max(counts.values()) / minority, 2)
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.25, random_state=42, stratify=y)
    cat = X.select_dtypes(include=['object']).columns.tolist(); num = [c for c in X.columns if c not in cat]
    def make_pipeline(clf):
        prep = ColumnTransformer([
            ('num', Pipeline([('impute', SimpleImputer(strategy='median')), ('scale', StandardScaler())]), num),
            ('cat', Pipeline([('impute', SimpleImputer(strategy='most_frequent')), ('encode', OneHotEncoder(handle_unknown='ignore'))]), cat)
        ])
        return Pipeline([('preprocess', prep), ('model', clf)])
    candidates = {
        'Logistic Regression': make_pipeline(LogisticRegression(max_iter=1500, class_weight='balanced')),
        'Random Forest': make_pipeline(RandomForestClassifier(n_estimators=250, random_state=42, class_weight='balanced', min_samples_leaf=2))
    }
    cv_splits = min(5, int(y_train.value_counts().min()))
    if cv_splits < 2: raise ValueError('Insufficient examples for stratified cross-validation.')
    cv = StratifiedKFold(n_splits=cv_splits, shuffle=True, random_state=42)
    scoring = {'precision':'precision', 'recall':'recall', 'f1':'f1', 'roc_auc':'roc_auc', 'accuracy':'accuracy'}
    results=[]; best_name=None; best_pipe=None; best_cv_f1=-1
    for name, pipe in candidates.items():
        scores = cross_validate(pipe, X_train, y_train, cv=cv, scoring=scoring, error_score='raise')
        pipe.fit(X_train, y_train)
        pred = pipe.predict(X_test); proba = pipe.predict_proba(X_test)[:, 1]
        metrics = {
            'model': name,
            'accuracy': round(float(accuracy_score(y_test, pred)), 4),
            'precision': round(float(precision_score(y_test, pred, zero_division=0)), 4),
            'recall': round(float(recall_score(y_test, pred, zero_division=0)), 4),
            'f1': round(float(f1_score(y_test, pred, zero_division=0)), 4),
            'roc_auc': round(float(roc_auc_score(y_test, proba)), 4) if y_test.nunique() == 2 else None,
            'brier_score': round(float(brier_score_loss(y_test, proba)), 4),
            'cv_f1_mean': round(float(scores['test_f1'].mean()), 4),
            'cv_f1_std': round(float(scores['test_f1'].std()), 4),
            'cv_precision_mean': round(float(scores['test_precision'].mean()), 4),
            'cv_recall_mean': round(float(scores['test_recall'].mean()), 4),
            'cv_roc_auc_mean': round(float(scores['test_roc_auc'].mean()), 4),
            'cv_folds': cv_splits,
            'confusion_matrix': confusion_matrix(y_test, pred, labels=[0,1]).tolist()
        }
        results.append(metrics)
        if metrics['cv_f1_mean'] > best_cv_f1:
            best_cv_f1=metrics['cv_f1_mean']; best_name=name; best_pipe=pipe
    # Calibrate probability estimates using training data only; test set remains held out.
    calibration_folds = min(3, int(y_train.value_counts().min()))
    calibrated = CalibratedClassifierCV(estimator=best_pipe, method='sigmoid', cv=calibration_folds)
    calibrated.fit(X_train, y_train)
    calibrated_proba = calibrated.predict_proba(X_test)[:, 1]
    for metric in results:
        if metric['model'] == best_name:
            metric['calibrated_brier_score'] = round(float(brier_score_loss(y_test, calibrated_proba)), 4)
            metric['calibration_method'] = 'sigmoid'
            metric['selected_by'] = 'mean cross-validation F1'
    # Final production bundle is fitted on all valid data; evaluation metrics above are holdout/CV only.
    final = CalibratedClassifierCV(estimator=make_pipeline(LogisticRegression(max_iter=1500, class_weight='balanced')) if best_name == 'Logistic Regression' else make_pipeline(RandomForestClassifier(n_estimators=250, random_state=42, class_weight='balanced', min_samples_leaf=2)), method='sigmoid', cv=min(3, int(y.value_counts().min())))
    final.fit(X, y)
    Path(model_dir).mkdir(parents=True, exist_ok=True)
    joblib.dump({'name':best_name, 'pipeline':final, 'features':FEATURES, 'calibrated':True, 'calibration_method':'sigmoid', 'class_counts':{'retained':int(counts.get(0,0)), 'attrited':int(counts.get(1,0))}, 'imbalance_ratio':imbalance_ratio}, Path(model_dir)/'best_model.joblib')
    return results, len(df), int(y.sum()), int(len(y)-y.sum())

def load_model(model_dir):
    path=Path(model_dir)/'best_model.joblib'
    if not path.exists(): return None
    return joblib.load(path)

def predict_probability(bundle, row):
    frame=pd.DataFrame([{k:row.get(k) for k in bundle['features']}])
    return float(bundle['pipeline'].predict_proba(frame)[0][1])
