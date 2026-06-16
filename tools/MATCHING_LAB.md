# JD/CV Matching Lab

Use this workflow to test JD and CV matching with human feedback.

## Folder Layout

Create one folder per match case:

```text
uploads/matching_lab/
  case_001/
    resume.pdf
    jd.pdf
    metadata.json
```

Supported file types:

- `.pdf`
- `.docx`
- `.doc`
- `.txt`

The tool detects files by name. Use names containing `resume`, `cv`, or `candidate` for the CV, and `jd`, `job`, `requirement`, or `job description` for the JD.

## Run Once

```bash
python tools/matching_lab.py --folder uploads/matching_lab
```

## Watch For New Cases

```bash
python tools/matching_lab.py --folder uploads/matching_lab --watch --interval 10
```

## Reprocess Existing Cases

```bash
python tools/matching_lab.py --folder uploads/matching_lab --force
```

## Generated Files

Each complete case gets:

```text
codex_prompt.md
match_result.json
match_result.md
human_review.json
```

Reviewers should update `human_review.json` after reading the result. This becomes the improvement dataset for CV parsing, JD parsing, and matching weights.

## Optional Metadata

`metadata.json` can contain context like:

```json
{
  "client": "Acme",
  "role": "Java Developer",
  "must_have_notes": ["Spring Boot", "Microservices"],
  "reviewer": "Recruiter Name"
}
```
