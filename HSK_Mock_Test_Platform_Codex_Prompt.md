# HSK Mock Test Platform - Full Stack Development Specification

## Role

You are a senior full-stack software engineer.

Build a complete production-ready web application for an online HSK (汉语水平考试) mock examination platform.

The platform must simulate the official HSK written examination experience for:

- HSK Level 1
- HSK Level 2
- HSK Level 3
- HSK Level 4
- HSK Level 5
- HSK Level 6


The system will allow students to:

- Register/login
- Select HSK level
- Take realistic timed mock exams
- Listen to audio sections
- Submit answers
- Receive automatic scoring
- Review mistakes
- Track learning progress


The administrator will manage:

- Mock exams
- Questions
- Audio files
- Users
- Test statistics
- Results


---

# 1. Product Vision

Create a professional HSK preparation platform similar to:

- Official HSK computer-based exam interface
- TOEFL/IELTS online practice platforms
- Modern language-learning SaaS platforms


The website should feel like a real examination environment.

The user should experience:

- Full-screen exam mode
- Countdown timer
- Section navigation
- Audio playback control
- Automatic answer saving
- Exam submission
- Detailed score report


---

# 2. HSK Exam Knowledge Base


## HSK 1

Sections:

Listening:
- 20 questions

Reading:
- 20 questions


Total:

Questions:
40

Time:
40 minutes

Maximum score:
200

Passing score:
120



---

## HSK 2

Sections:

Listening:
35 questions

Reading:
25 questions


Total:

Questions:
60

Time:
55 minutes

Maximum score:
200

Passing score:
120



---

## HSK 3

Sections:

Listening:
40 questions

Reading:
30 questions

Writing:
10 questions


Total:

Questions:
80

Time:
90 minutes

Maximum score:
300

Passing score:
180



---

## HSK 4

Sections:

Listening:
45 questions

Reading:
40 questions

Writing:
15 questions


Total:

Questions:
100

Time:
105 minutes

Maximum score:
300

Passing score:
180



---

## HSK 5

Sections:

Listening:
45 questions

Reading:
45 questions

Writing:
10 questions


Total:

Questions:
100

Time:
125 minutes

Maximum score:
300

Passing score:
180



---

## HSK 6

Sections:

Listening:
50 questions

Reading:
50 questions

Writing:
1 summary writing task


Total:

Questions:
101

Time:
140 minutes

Maximum score:
300

Passing score:
180


---

# 3. Recommended Technology Stack


## Frontend

Framework:

Vue 3


Build:

Vite


Language:

TypeScript


Libraries:

- Vue Router
- Pinia state management
- Axios
- Element Plus UI
- TailwindCSS
- VueUse


Features:

- Responsive design
- Exam interface
- Timer
- Audio player
- Result dashboard



---

## Backend

Framework:

FastAPI


Language:

Python 3.12


Libraries:

- SQLAlchemy ORM
- Pydantic
- JWT Authentication
- Alembic migrations
- Celery background jobs


API Style:

REST API


---

## Database

MySQL 8


Use for:

- Users
- Exams
- Questions
- Answers
- Results
- Statistics


---

## Additional Services


Redis:

Purpose:

- Exam timer storage
- Session management
- Cache


File Storage:

MinIO or AWS S3 compatible storage


Store:

- Listening audio
- Images
- Exam PDFs
- User uploads


Deployment:

Docker + Docker Compose



---

# 4. System Architecture


Create:


Frontend:

Vue Application

|

REST API

|

FastAPI Backend

|

Services Layer

|

Database


---

# 5. User Roles


## Student


Permissions:

- Register account
- Login
- Browse HSK levels
- Start exams
- Save answers
- Submit exams
- View scores
- Review mistakes
- View progress history


---

## Admin


Permissions:

Full CRUD:


Users:

- View
- Disable
- Delete


Exams:

- Create
- Edit
- Delete
- Publish


Questions:

- Add
- Edit
- Delete


Audio:

- Upload
- Replace
- Delete


Statistics:

- Number of attempts
- Average score
- Pass rate
- Popular levels


---

# 6. Database Design


Create database schema.



## users table


Fields:

id

username

email

password_hash

role

created_at

updated_at



Roles:

student

admin



---


## hsk_levels table


Fields:

id

level

name

total_questions

duration_minutes

max_score

passing_score



Example:


HSK 1

duration:
40


score:
200



---


## exams table


Fields:


id

level_id

title

description

status

created_at



Status:

draft

published



---


## sections table


Fields:


id

exam_id

section_type

question_count

score_weight



section_type:


LISTENING

READING

WRITING



---


## questions table


Fields:


id

section_id

question_number

question_type

content

audio_url

image_url

correct_answer

score



question_type examples:


multiple_choice

true_false

fill_blank

sentence_order

writing



---


## options table


Fields:


id

question_id

option_label

option_text



Example:


A

苹果



B

香蕉



---


## attempts table


Store every exam attempt.


Fields:


id

user_id

exam_id

start_time

end_time

status

total_score



---


## answers table


Fields:


id

attempt_id

question_id

user_answer

is_correct

score



---


## progress table


Track:


user_id

level

attempt_count

average_score

highest_score



---

# 7. Exam Engine


Develop a complete exam engine.


Requirements:


## Timer


When user starts:

Create exam session.


Timer starts.


Save timer state in Redis.


If browser closes:

User can continue.


When time reaches zero:

Automatically submit.



---

## Answer Auto Save


Every answer selection:

Immediately save using API.


Prevent data loss.



---

## Exam Navigation


Interface:


Left side:

Question list


Example:

1 2 3 4 5


Completed:

green


Current:

blue


Not answered:

gray



Right side:

Question area



---

# 8. Listening Module


Requirements:


Audio player:


Features:


- Play
- Pause
- Volume
- Progress bar


Restrictions:


During real exam simulation:

Audio cannot restart after first play.


Admin can configure:


audio_play_limit


Example:

HSK listening:

1 play



---

# 9. Question Types


Support:


## Multiple Choice


Example:


你叫什么？

A. 我叫李明

B. 北京

C. 苹果


---

## True False


判断:

正确 / 错误


---

## Fill Blank


Example:


我___学生。


---

## Sentence Ordering


Example:


Arrange:


喜欢

我

学习中文



Answer:


我喜欢学习中文



---

## Writing


Support:


- Chinese character input
- Text area
- Character counter


For HSK6:


Essay summary.


---

# 10. Scoring System


Automatic scoring:


Listening:

100 points


Reading:

100 points


Writing:

100 points



For HSK1/2:


Listening:

100


Reading:

100



Generate:


Score:

178/300


Status:


PASS

or

FAIL



---

# 11. Result Page


After submission:


Display:


## Summary


HSK Level:

HSK 4


Score:

230/300


Result:

PASS



---

## Section Analysis


Listening:

80/100


Reading:

75/100


Writing:

75/100



---

## Question Review


Show:


Question

User answer

Correct answer

Explanation



---

# 12. Admin Dashboard


Build dashboard.


Components:


Cards:


Total users

Total exams

Total attempts

Average score



Charts:


- User growth
- Exam popularity
- Pass rate


Tables:


Recent attempts

Recent registrations



---

# 13. File Management


Admin can upload:


Exam:

JSON


Audio:

MP3


Images:

PNG/JPG


PDF:



Example structure:


/storage

    /hsk1

        /listening

        /reading

        /audio



---

# 14. API Design


Create:


Authentication:


POST

/api/auth/register


POST

/api/auth/login



---

Exam:


GET

/api/exams


GET

/api/exams/{id}


POST

/api/exams/{id}/start



---

Questions:


GET

/api/exams/{id}/questions



---

Answers:


POST

/api/attempt/{id}/answer



---

Submit:


POST

/api/attempt/{id}/submit



---

Results:


GET

/api/results/{id}



---

Admin:


POST

/api/admin/exam


PUT

/api/admin/question


DELETE

/api/admin/question



---

# 15. Frontend Pages


Create:


## Public


Home page


Features:

- HSK introduction
- Level selection
- Login


---

Login/Register


---

HSK Level Page


Display:


HSK1

HSK2

HSK3

HSK4

HSK5

HSK6



---

# Student Pages


Dashboard


Shows:


Recent tests

Scores

Progress



---

Exam Page


Full-screen simulation.



---

Result Page


Score analysis.



---

# Admin Pages


Admin dashboard


Exam management


Question management


User management


Statistics



---

# 16. Security Requirements


Implement:


- Password hashing
- JWT authentication
- Role-based authorization
- Input validation
- SQL injection protection
- File upload validation


---

# 17. Docker Deployment


Create:


docker-compose.yml


Services:


frontend

backend

mysql

redis

minio



---

# 18. Development Requirements


Generate:


Complete source code.


Include:


README.md


Installation guide.


Environment variables:


.env.example



Database migration scripts.


Sample data:


HSK1 demo exam


Admin account


Student account



---

# 19. Future Expansion


Design architecture allowing:


- HSK 7-9
- HSKK Speaking test
- AI writing evaluation
- Vocabulary learning
- Flashcards
- Subscription system
- Payment gateway
- Mobile application


---

# Final Goal


Deliver a professional HSK online mock examination platform that can support thousands of students and replicate the real HSK 1-6 exam experience.