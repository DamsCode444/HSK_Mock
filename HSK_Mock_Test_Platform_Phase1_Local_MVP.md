Yes, after seeing your actual data structure, I would **change the development strategy**.

For the first version, I do **not recommend Docker**. Since this is a new project and you need to quickly validate:

1. Can the exam parser correctly read your PDF bundles?
2. Can the audio mapping work?
3. Can the HSK exam UI reproduce the real exam?
4. Can scoring work correctly?

A local development environment is much faster.

Later, after the MVP is stable:

* Dockerize backend/frontend/database
* Deploy to cloud
* Add user subscription/payment system

The first Codex prompt should focus on:

**Phase 1: Local MVP → Content ingestion → Student exam system → Admin upload**

Your current file structure is actually very suitable:

```
HSK_mock_test_bundles_exam_answers_audio_file/

│
├── HSK1
│   │
│   ├── mock-test-HSK1-H11329
│   │       │
│   │       ├── mock-test-HSK1-H11329-audios/
│   │       │       ├── 001.mp3
│   │       │       ├── 002.mp3
│   │       │       └── ...
│   │       │
│   │       ├── mock-test-HSK1-H11329-exam.pdf
│   │       │
│   │       └── mock-test-HSK1-H11329-answer.pdf
│
│
├── HSK2
│
├── HSK3
│
├── HSK4
│
├── HSK5
│
└── HSK6
        │
        ├── exam.pdf
        ├── answers.pdf
        ├── writing.pdf
        └── audios/
```

This means we need an **automatic PDF + audio ingestion pipeline**.

---

# Updated Codex Prompt

Save as:

`HSK_Mock_Test_Platform_Phase1_Local_MVP.md`

---

```md
# HSK Mock Test Platform - Phase 1 Local MVP Development


## Role

You are a senior full-stack developer.

Build a local development version of an HSK (汉语水平考试) mock testing platform.

The purpose of this phase is to create a working MVP using my existing HSK mock test bundle files.

Do NOT use Docker.

The application must run locally on Windows/Linux.


---

# Current Data Source


I already have official-style HSK mock test bundles organized as:


```

HSK_mock_test_bundles_exam_answers_audio_file/

├── HSK1/

│   ├── mock-test-HSK1-H11329/

│   │
│   │── mock-test-HSK1-H11329-exam.pdf
│   │
│   │── mock-test-HSK1-H11329-answer.pdf
│   │
│   │── mock-test-HSK1-H11329-audios/

├── HSK2/

├── HSK3/

├── HSK4/

├── HSK5/

└── HSK6/

```


Each mock test contains:

- Exam PDF
- Answer PDF
- Listening MP3 audio folder
- HSK6 additionally contains writing PDF


The system must automatically import these files.



---

# Development Technology


## Frontend


Vue 3

Vite

JavaScript

Axios

Pinia

Vue Router

Element Plus

TailwindCSS



---

## Backend


Python

FastAPI


Libraries:

- SQLAlchemy
- Pydantic
- PyJWT
- bcrypt
- PyMuPDF
- pdfplumber


---

## Database


MySQL


Local installation only.


---

# Project Structure


Create:


```

HSK_mockTester/

frontend/

backend/

database/

storage/

scripts/

README.md

```



---

# Phase 1 Main Goals


Build:


1.
Automatic HSK bundle importer


2.
Student exam system


3.
Automatic scoring


4.
Listening audio system


5.
Result analysis


6.
Simple admin panel



---

# 1. HSK Bundle Import System


Create Python scripts:


```

scripts/import_hsk_tests.py

```


The script should:


Scan:


```

HSK_mock_test_bundles_exam_answers_audio_file/

```


Automatically detect:


- HSK level
- Test ID
- Exam PDF
- Answer PDF
- Audio files


Example:


Input:


```

mock-test-HSK1-H11329

```


Extract:


level:

HSK1


test_code:

H11329


exam_file:

exam.pdf


answer_file:

answer.pdf


audio_folder:

audios/


---

# 2. PDF Processing


Use:


PyMuPDF


Extract:


Exam questions from PDF.


Store:


Question number

Section

Question text

Options

Images if available



---

# 3. Answer PDF Processing


Read answer PDF.


Extract:


Question number

Correct answer


Example:


```

1 A

2 C

3 B

```


Store automatically.


---

# 4. Database Design


Create MySQL tables.



## users


id

username

email

password_hash

role

created_at



Roles:

student

admin



---


## hsk_tests


id

level

test_code

title

duration

status



Example:


HSK1

H11329


---


## questions


id

test_id

section

number

question_text

question_type

audio_file

correct_answer



Sections:


LISTENING

READING

WRITING



---


## options


id

question_id

label

text



---


## attempts


id

user_id

test_id

start_time

end_time

score



---


## answers


id

attempt_id

question_id

user_answer

correct

score



---

# 5. Exam Interface


Create a realistic HSK computer exam interface.


Layout:


------------------------------------------------


LEFT:


Question navigation


1 2 3 4 5


Colors:


Answered

Current

Not answered



RIGHT:


Question content



BOTTOM:


Previous

Next

Submit



------------------------------------------------



---

# 6. Listening Exam


Implement:


Audio player.


Features:


- Play
- Pause
- Volume
- Progress


Admin setting:


allow_replay


For HSK simulation:


default:

one replay only



---

# 7. Exam Timer


When exam starts:


Start countdown.


Save timer locally.


If browser refreshes:


Recover session.



When time reaches zero:


Auto submit.



---

# 8. Scoring


Implement official scoring:


HSK1:


Listening 100

Reading 100


Total:

200



HSK2:


Listening 100

Reading 100



HSK3-6:


Listening:

100


Reading:

100


Writing:

100



Generate:


Score report:


Example:


```

HSK3 Mock Test

Listening:

82/100

Reading:

76/100

Writing:

70/100

Total:

228/300

PASS

```



---

# 9. Student Dashboard


Show:


Previous attempts


Scores


Accuracy


Weak sections



---

# 10. Admin Dashboard


Simple version.


Features:


Upload new HSK folder


View imported tests


Delete tests


View students



---

# 11. File Storage


Do not upload files into database.


Use:


```

storage/

HSK1/

H11329/

audio/

pdf/

```



Database stores paths.



---

# 12. Authentication


Implement:


JWT login.


Student registration.


Admin login.



---

# 13. Local Running Instructions


Provide:


## Backend


```

cd backend

python -m venv venv

pip install -r requirements.txt

uvicorn main:app --reload

```



## Frontend


```

cd frontend

npm install

npm run dev

```



---

# 14. Development Order


Follow this order:


STEP 1:

Create database models.


STEP 2:

Create importer script.


STEP 3:

Import HSK1 sample.


STEP 4:

Create exam API.


STEP 5:

Create Vue exam page.


STEP 6:

Implement scoring.


STEP 7:

Add HSK2-6.


STEP 8:

Add admin panel.



---

# Important


Do not manually create questions.

The system must be designed to ingest my provided PDF and audio bundles.

The first successful milestone:

Import:

HSK1-H11329


and allow a student to complete the full listening + reading exam online.



After MVP completion, prepare architecture for future:

- Docker
- Cloud deployment
- Subscription system
- AI Chinese writing evaluation
- HSK speaking test
- Mobile app

```

---

My recommendation: **Do not ask Codex to build everything at once.** Give it this Phase 1 prompt first. The biggest technical challenge is not Vue/FastAPI — it is **reliably converting your PDF exam bundles into structured questions + mapping MP3 audio to questions**. Once this pipeline works, the rest is straightforward.
