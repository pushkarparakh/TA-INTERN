# Intern task: checking an AI comment moderator

This README is short on purpose. Use AI to research/understand anything not explained
here: GenWise, Navin Kabra's background, Cloudflare Workers AI, Clef, and so on. That is
part of the task. The task looks like a programming-heavy task, but it doesn't require you to be a programmer: you can use AI to get the program written (and checked into GitHub). I know enough non-programmers who are able to do that now.

## Background

GenWise is working with a nationally recognised brand to run a 5-month online course on
Generative AI for college students across India. We expect about 10,000 students.

The course runs for 20 weeks on our own learning platform. Each week has short videos,
a practical article or two, hands-on exercises with free AI tools such as ChatGPT,
Claude and Gemini, and a quiz. Students submit exercise answers each week, ask questions
in forums, and can join a live online session once a month. A student must finish one
week before the next opens. Students who complete the course get a certificate.

The course assumes that the students only have access to free tiers of the various AI platforms/models; so it will not be a very advanced AI course. It will mostly be about relatively advanced use cases that fit within the free tiers.

## The TA role

The work involves answering student questions, and working with Navin to build AI-based
systems for monitoring and evaluation, and then monitoring and evaluating those systems.

A large part of it is manual and repetitive, so be clear about that before you apply.
You will use AI to automate the repetitive work, but you will still have to check the
AI's work for mistakes. Together with the AI, you will do the following:

- **Forums.** Reading student posts every day, answering questions, and spotting posts
  that are abusive, spam, or off-topic.
- **Exercise answers.** Reading student submissions, checking them against the rubric,
  and judging cases the automated checks get wrong or are unsure about.
- **Checking the AI.** We will use AI to filter forum posts and to give a first
  evaluation of answers. These systems make mistakes. Your job is to read their output
  closely, find where they are wrong, explain why, and help us improve them.
- **Developing new AI tools.** Building and using AI automation to make your job easier.
  This part will be interesting and exciting, but do not expect it to take much of your
  time.

The task below is a small version of "Checking the AI".

### Work details

- **Hours:** about 10 hours a week, all remote. You choose when to work, but expect
  about an hour every day, and more on a couple of days, probably around weekends.
- **No missed days:** we promise students a maximum time for a forum question to wait
  for an answer, so you cannot skip a day entirely unless you have agreed it with Navin
  in advance.
- **Live sessions:** 5 live online sessions, one Saturday a month. You must be available
  for two hours at each. The dates and times will be shared well in advance.
- **Pay:** ₹10,000 a month.

# The Task

`comments.json` has 100 forum comments from a made-up college course. Each one is
**acceptable**, **toxic** or **spam**.

1. Click the green **Use this template** button at the top of this repository's GitHub page to make your own public copy.
2. Use AI to clone your copy (created after you click on "Use this template") on your computer.
3. Get a free Cloudflare account and an API token for Workers AI. Put your account ID and token in a copy of `cloud-flare.sh` named `cloud-flare.local.sh`.
4. Write a Python program that uses Cloudflare's **Clef** model to classify each comment as acceptable, toxic or spam. [CLEF_API.md](CLEF_API.md) explains the API and has sample code.
5. Have the program write an HTML page that shows each comment with its
   classification, and is easy to scan.
6. Create an empty file called `MISTAKES.md`. Then, read every comment and its classification yourself to check Clef's work. Wherever Clef made a mistake, add the comment to `MISTAKES.md` with:
   - the comment id;
   - Clef's label, and the label you think is right;
   - one or two sentences on why.

   If a comment is borderline, say so and explain your choice.

Use AI tools as much as you like for steps 1 to 5. Step 6 is about your own judgement, and is the most important part of the task: do not ask an AI to do it for you.

## How to submit

1. At this point, you will have your own copy of the repository.
2. To the repository, add your program, the generated HTML, and the `MISTAKES.md` file.
3. Create a new file called `NOTES.md`. In this, add a few lines indicating how to run your program. Then add a short description of what tools/models you used to complete this task, and overall what you felt about doing this.
4. Before you push, make sure that your API token is not in any file that will get committed and pushed. This repository has been configured to not check in the `cloud-flare.local.sh` file, which contains your API token.
5. Commit and push your changes to GitHub. Then check on GitHub that `cloud-flare.local.sh` did not get pushed.
6. Email the repository link to navin@genwise.in.

## Notes

1. If you have questions that you want answered before doing this task, you can email or WhatsApp Navin.
2. If it is taking you more than 1 hour to do this task, you are doing something wrong, or not using AI effectively. Check with your AI how this can be speeded up.
