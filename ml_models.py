import numpy as np
from sklearn.linear_model import LogisticRegression, LinearRegression


# ================= RISK PREDICTION =================
def predict_risk_from_db(student_features, all_students_data):

    if len(all_students_data) < 3:
        return "Not Enough Data"

    X = []
    y = []

    for row in all_students_data:
        X.append(row[:4])
        y.append(row[4])

    X = np.array(X)
    y = np.array(y)

    model = LogisticRegression(max_iter=1000)
    model.fit(X, y)

    prediction = model.predict([student_features])[0]

    risk_map = {
        0: "Low Risk",
        1: "Medium Risk",
        2: "High Risk"
    }

    return risk_map[prediction]


# ================= NEXT SCORE PREDICTION =================
def predict_next_score(previous_marks):

    if len(previous_marks) < 2:
        return None

    import numpy as np
    from sklearn.linear_model import LinearRegression

    X = np.arange(len(previous_marks)).reshape(-1, 1)
    y = np.array(previous_marks)

    model = LinearRegression()
    model.fit(X, y)

    next_index = np.array([[len(previous_marks)]])
    
    prediction = model.predict(next_index)[0]
    if prediction > 5:
        prediction = 5 - (prediction - 5) * 0.3

    if prediction < 0:
        prediction = 0

    return round(float(prediction), 2)


# ================= AI RECOMMENDATION =================
def generate_recommendation(risk_level, avg_similarity, late_count):

    if risk_level == "High Risk":
      return "Your performance is declining. Focus on improving marks and reducing late submissions."

    if risk_level == "Medium Risk":
        return "You are performing moderately. Improve consistency and avoid plagiarism."

    if risk_level == "Low Risk":
        return "Excellent performance. Maintain your consistency."

    return "Not enough data to generate recommendation."