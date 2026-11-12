<p align="center"><img src="https://mahmoudyosrimahmoud13.github.io/inPace/assets/icon.svg" width="80" alt="inPace logo"></p>

<h1 align="center">inPace course library</h1>
<p align="center"><b>Free courses made and shared by people who learn with <a href="https://github.com/mahmoudyosrimahmoud13/inpace">inPace</a>.</b><br>
<a href="https://mahmoudyosrimahmoud13.github.io/inpace-library/"><b>Browse the library</b></a> (English and Arabic) · <a href="../../issues/new?template=submit-course.yml"><b>Share your course</b></a></p>

---

## Add a course to your inPace

- **In the app:** open **Course library** in the sidebar and press **Add**.
- **On the web:** open the [library page](https://mahmoudyosrimahmoud13.github.io/inpace-library/) and press **Add to inPace**.
- **From a friend:** tap the course link they sent you.

The app checks every course against the library's list before adding it. Your progress stays on your computer.

## Share your own course

1. Make the course in inPace (by hand, with AI, or from a folder of videos).
2. In **My courses**, open **More** on the course and choose **Publish to the library…**
3. Press **Download** to get the course file. It's signed with your inPace key, so the library knows it's yours.
4. Press **Open the form**. It opens [the submission form](../../issues/new?template=submit-course.yml) with your course details filled in.
5. Drag the course file into the form and press **Submit**.

A bot checks the course within a few minutes and replies in the form. If something needs fixing, edit the form (for
example, attach a new file) and it checks again. When it passes, it opens a pull request, and a maintainer adds the
course to the library.

**To update your course,** change it in inPace and publish it again the same way. Only you can update it, because
only your inPace key can sign it.

## Courses with videos

The library keeps each course under 20 MB, so big videos don't live here. Instead:

- **Use YouTube or Vimeo links** in your lessons, or
- **Upload the videos somewhere people can download them** (Google Drive, Dropbox, MEGA, archive.org…) and add the
  link in inPace: **Edit → Course details → Where to download the course's videos and files**.

Learners see a **Get this course's videos** button, download the files, and choose the folder in inPace. The course
then finds every video by itself.

## Rules

- **Only share what you made** (by yourself or with AI). No copied books, paid courses, or videos you don't have the
  right to share.
- **Everything here is public,** including quiz answers. Quizzes from the library are for practice. Checkers can add
  their own private questions for verified exams.
- **Choose a license** when you submit. CC BY 4.0 is a good default: anyone can use and share your course, and must
  credit you.
- **Keep it kind and useful.** Courses with harmful content are removed.

See a problem with a course? [Report it](../../issues/new?template=report.yml).

## How it works

```text
courses/<id>/              one folder per course
  course.yaml, lessons/,   the course itself (the same format as inPace's course files)
  questions.yaml, answers.yaml
  files/                   small files that come with it, like its cover picture
  inpace-author.json       the author's signature (name, inPace key, course fingerprint)
  library.yaml             license, tags, who submitted it, when
scripts/library_tools.py   checks submissions, checks all courses, builds the site
.github/workflows/
  submission.yml           a submission form was opened or edited: check it, reply, open a pull request
  check.yml                every pull request: check every course
  publish.yml              every merge: build library.json, the course files and the page, put them on GitHub Pages
  labels.yml               makes the labels the forms use
```

The site at `mahmoudyosrimahmoud13.github.io/inpace-library/` has:

- `library.json`, the list the app reads,
- `packs/<id>.zip`, each course, with a SHA-256 checksum in the list,
- `covers/`, the course pictures,
- `index.html`, the library page.

## Setup (maintainers, once)

1. **Settings → Pages → Source: GitHub Actions.**
2. **Settings → Actions → General → Workflow permissions:** choose **Read and write permissions** and tick
   **Allow GitHub Actions to create and approve pull requests**.
3. **Actions → Make labels → Run workflow**, once.
4. Protect `main` so changes come through reviewed pull requests.

## License

The tools in this repository are MIT licensed. Each course has its own license, shown in its `library.yaml` and on
the library page.
