# Dataset documentation

`hr_attrition_dataset.csv` contains 500 **synthetic** employee records generated for software demonstration. It is not real employee data and is not copied from a public benchmark.

| Column | Meaning |
|---|---|
| EmployeeNumber | Unique sample employee identifier |
| Age | Employee age in years |
| Department | Sample department |
| JobRole | Sample role/designation |
| MonthlyIncome | Synthetic monthly salary in INR |
| JobSatisfaction | Ordinal score 1–4 |
| WorkLifeBalance | Ordinal score 1–4 |
| OverTime | Yes / No |
| YearsAtCompany | Tenure in years |
| YearsSinceLastPromotion | Years since last promotion |
| TrainingTimesLastYear | Number of training sessions last year |
| PerformanceRating | Ordinal performance rating 1–4 |
| AbsentDaysLastYear | Absence days last year |
| Attrition | Target label: Yes / No |
| Gender | Synthetic demographic category |
| MaritalStatus | Synthetic marital status category |

The target was sampled using a deliberately simple probability formula involving several input fields. Therefore it contains artificial patterns and must not be interpreted as evidence about real workers.
