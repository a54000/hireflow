
var currentUser = { is_admin: false, team_member_id: null, username: '', loaded: false };
let cvParsedData = null;
let currentCandidateId = null;
let allRequirementOptions = [];
let pendingStatusChange = null;
let dashboardRows = [];
let dashboardCandidatePage = 1;
let dashboardCandidatePagination = {page:1,page_size:15,total:0,total_pages:1};
const dashboardCandidatePageSize = 15;
let dashboardCandidateSearchTimer = null;
let suppressWorkspaceAutoLoad = false;
let summaryRecruiterView = 'month';
let summaryClientView = 'month';
let summaryNoSubmissionTodayExpanded = false;
let dashboardSummaryFullLoaded = false;
let dashboardSummaryIdleScheduled = false;
const atsReferenceCache = {skills:null, requirements:null, team:null};
const loadedTabData = new Set();
let dashboardViewState = {
  groupBy: '',
  sortBy: 'date',
  sortDir: 'desc',
  filters: {},
  filterDrafts: [['name', '']],
  hidden: {role:true, phone:true, email:true}
};
try {
  const dashboardViewVersion = '4';
  if (localStorage.getItem('hrguru_dashboard_view_state_version') === dashboardViewVersion) {
    dashboardViewState = {...dashboardViewState, ...(JSON.parse(localStorage.getItem('hrguru_dashboard_view_state') || '{}') || {})};
  } else {
    localStorage.setItem('hrguru_dashboard_view_state_version', dashboardViewVersion);
    localStorage.setItem('hrguru_dashboard_view_state', JSON.stringify(dashboardViewState));
  }
  if (dashboardViewState.hidden) {
    dashboardViewState.hidden.requirement = false;
    dashboardViewState.hidden.client = false;
    dashboardViewState.hidden.status = false;
    dashboardViewState.hidden.recruiter = false;
    dashboardViewState.hidden.communication = false;
  }
  if (!Array.isArray(dashboardViewState.filterDrafts) || !dashboardViewState.filterDrafts.length) {
    dashboardViewState.filterDrafts = Object.entries(dashboardViewState.filters || {}).length
      ? Object.entries(dashboardViewState.filters)
      : [['date', '']];
  }
} catch(e) {}
const CANDIDATE_STATUSES = ["New","Shortlisted","Screening Pending","Screen Rejected","Interviewed","HM Rejected","Offered","Joined","Dropped","Duplicate","OnHold"];
const candidateColumns = [
  {key:'created', label:'Date'},
  {key:'name', label:'Name', required:true},
  {key:'requirement', label:'Requirement'},
  {key:'role', label:'Role'},
  {key:'client', label:'Client'},
  {key:'company', label:'Current company'},
  {key:'email', label:'Email'},
  {key:'phone', label:'Phone'},
  {key:'status', label:'Status', required:true},
  {key:'experience', label:'Experience'},
  {key:'skills', label:'Skills'},
  {key:'location', label:'Location'},
  {key:'notice', label:'Notice period'},
  {key:'recruiter', label:'Recruiter'},
  {key:'contact', label:'Communication', required:true}
];
const defaultCandidateColumns = {
  created:true, name:true, requirement:true, role:false, client:true, company:false, email:false, phone:false,
  status:true, experience:false, skills:false, location:false, notice:false,
  recruiter:true, contact:true
};
const columnStorageVersion = '5';
if (localStorage.getItem('hrguru_candidate_columns_version') !== columnStorageVersion) {
  localStorage.setItem('hrguru_candidate_columns', JSON.stringify(defaultCandidateColumns));
  localStorage.setItem('hrguru_candidate_columns_version', columnStorageVersion);
}
let visibleCandidateColumns = JSON.parse(localStorage.getItem('hrguru_candidate_columns') || 'null') || {...defaultCandidateColumns};



// Debug function
window.testReqModal = function() { showToast('Opening requirement form', 'success'); showAddRequirementModal(); };
function showToast(message, type='error', duration=4000) {
  var t = document.getElementById('toast');
  if (!t) {
    t = document.createElement('div');
    t.id = 'toast';
    t.style.position = 'fixed';
    t.style.top = '20px';
    t.style.right = '20px';
    t.style.padding = '12px 16px';
    t.style.borderRadius = '8px';
    t.style.zIndex = '9999';
    t.style.color = '#fff';
    t.style.fontFamily = 'sans-serif';
    t.style.boxShadow = '0 4px 12px rgba(0,0,0,.3)';
    document.body.appendChild(t);
  }
  t.textContent = message;
  t.style.display = 'block';
  t.style.background = type === 'success' ? '#2ecc71' : (type === 'info' ? '#2d96cf' : '#e74c3c');
  t.style.opacity = '1';
  t.style.transition = 'opacity 0.3s ease';
  setTimeout(() => { t.style.display = 'none'; }, duration);
}

function confirmAction({title='Confirm action', message='Are you sure?', okText='Confirm', danger=true} = {}) {
  return new Promise(resolve => {
    const modal = document.getElementById('confirmModal');
    const titleEl = document.getElementById('confirmTitle');
    const messageEl = document.getElementById('confirmMessage');
    const okBtn = document.getElementById('confirmOkBtn');
    const cancelBtn = document.getElementById('confirmCancelBtn');
    titleEl.textContent = title;
    messageEl.textContent = message;
    okBtn.textContent = okText;
    okBtn.className = danger ? 'btn btn-danger' : 'btn';
    const cleanup = result => {
      modal.classList.remove('active');
      okBtn.onclick = null;
      cancelBtn.onclick = null;
      resolve(result);
    };
    okBtn.onclick = () => cleanup(true);
    cancelBtn.onclick = () => cleanup(false);
    modal.classList.add('active');
  });
}

function showAlertPopup({title='Notice', message='', okText='OK'} = {}) {
  return new Promise(resolve => {
    const modal = document.getElementById('confirmModal');
    const titleEl = document.getElementById('confirmTitle');
    const messageEl = document.getElementById('confirmMessage');
    const okBtn = document.getElementById('confirmOkBtn');
    const cancelBtn = document.getElementById('confirmCancelBtn');
    titleEl.textContent = title;
    messageEl.textContent = message;
    okBtn.textContent = okText;
    okBtn.className = 'btn';
    cancelBtn.style.display = 'none';
    const cleanup = () => {
      modal.classList.remove('active');
      okBtn.onclick = null;
      cancelBtn.style.display = '';
      resolve(true);
    };
    okBtn.onclick = cleanup;
    modal.classList.add('active');
  });
}

let emailTemplates = {};
window.cachedClientOptions = null;
window.cachedAllClientOptions = null;

function cacheClientOptions(rows, all=false) {
  const safeRows = Array.isArray(rows) ? rows : [];
  if (all) {
    window.cachedAllClientOptions = safeRows;
  } else {
    window.cachedClientOptions = safeRows;
  }
  return safeRows;
}

async function getClientOptionsCached({all=false, force=false} = {}) {
  const cached = all ? window.cachedAllClientOptions : window.cachedClientOptions;
  if (!force && Array.isArray(cached)) return cached;
  const url = all ? '/api/clients?all=1' : '/api/clients';
  const rows = await fetch(url).then(r => r.json()).catch(() => []);
  return cacheClientOptions(rows, all);
}

function populateRequirementClientSelect(rows) {
  const sel = document.getElementById('reqClientSel');
  if (!sel) return;
  sel.replaceChildren();
  const placeholder = document.createElement('option');
  placeholder.value = '';
  placeholder.textContent = 'Select Client...';
  sel.appendChild(placeholder);
  const safeRows = Array.isArray(rows) ? rows : [];
  safeRows.forEach(c => {
    const name = String(c.client_name || '').trim();
    if (!name) return;
    const opt = document.createElement('option');
    opt.value = name;
    opt.textContent = name;
    sel.appendChild(opt);
  });
}

function escapeRegExp(text) {
  return String(text || '').replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

function unwrapTemplateBraces(text, variables) {
  let output = text || '';
  Object.values(variables).forEach(value => {
    const clean = String(value || '').trim();
    if (!clean) return;
    output = output.replace(new RegExp('\\{\\s*' + escapeRegExp(clean) + '\\s*\\}', 'g'), clean);
  });
  return output;
}

async function fetchEmailTemplates() {
    const res = await fetch('/api/email_templates');
    const templates = await res.json();

    const sel = document.getElementById('emailTemplate');
    if (!sel) return;
    const current = sel.value;
    sel.innerHTML = '<option value="">Select template...</option>';
    emailTemplates = {};

    templates.forEach(t => {
        emailTemplates[String(t.id)] = t;

        const opt = document.createElement('option');
        opt.value = t.id;
        opt.textContent = t.name;
        sel.appendChild(opt);
    });
    if (current) sel.value = current;
}

let isLoadingTemplate = false;

function loadEmailTemplate() {
    const type = document.getElementById("emailTemplate").value;
    if (!type || !emailTemplates[String(type)]) return;
    const tpl = JSON.parse(JSON.stringify(emailTemplates[String(type)]));

    const c = window.currentCandidate || {};
    const candidateName = c.candidate_name || document.getElementById("detailName").textContent.trim();
    const role = c.role_name || c.current_role || document.getElementById("detailRole").textContent.trim();
    const company = c.client_name || c.requirement_client || c.current_company || document.getElementById("detailCompany").textContent.trim();
    const recruiter = c.recruiter_name || document.getElementById("detailRecruiter").textContent.trim();
    const candStatus = c.status || document.getElementById("detailStatus").textContent.trim();

    let subject = tpl.subject;
    let body = tpl.body;
    const variables = {
      candidate_name: candidateName,
      name: candidateName,
      role_name: role,
      role: role,
      current_role: c.current_role || role,
      company: company,
      current_company: company,
      recruiter_name: recruiter,
      status: candStatus,
      email_addr: c.email_addr || '',
      phone: c.phone || ''
    };

    Object.keys(variables).forEach(key => {
      const value = variables[key] || '';
      subject = subject.replaceAll('{{' + key + '}}', value).replaceAll('{' + key + '}', value);
      body = body.replaceAll('{{' + key + '}}', value).replaceAll('{' + key + '}', value);
    });
    subject = unwrapTemplateBraces(subject, variables);
    body = unwrapTemplateBraces(body, variables);

    document.getElementById("emailSubject").value = subject;
    document.getElementById("emailBody").value = body;
}

function showEmailError(message) {
    const el = document.getElementById("emailAlert");
    if (!el) return;
    let friendly = message || "Failed to send email";
    if (friendly.toLowerCase().includes("smtp not configured")) {
      friendly = "Please log in with Google again before sending email.";
    }
    el.textContent = friendly;
    el.style.display = "block";
    el.style.background = "#4a2b2b";
    el.style.color = "#ffb3b3";
}

function clearEmailError() {
    const el = document.getElementById("emailAlert");
    if (el) {
      el.textContent = "";
      el.style.display = "none";
    }
}

function statusOptions(selected='') {
  return CANDIDATE_STATUSES.map(s => `<option value="${s}" ${s===selected?'selected':''}>${s}</option>`).join('');
}

function openEmailModal() {
    clearEmailError();
    if (!Object.keys(emailTemplates || {}).length) {
      fetchEmailTemplates();
    }
    document.getElementById("emailModal").classList.add("active");
    document.getElementById("emailTo").value =
        (window.currentCandidate && window.currentCandidate.email_addr) || document.getElementById("detailEmail").innerText;
    const templateSelect = document.getElementById("emailTemplate");
    if (templateSelect.value) loadEmailTemplate();
}

async function sendEmail() {
    const btn = document.getElementById("sendEmailBtn");
    clearEmailError();

    btn.disabled = true;
    btn.innerText = "Sending...";

    const to = document.getElementById("emailTo").value.trim();
    const subject = document.getElementById("emailSubject").value.trim();
    const body = document.getElementById("emailBody").value.trim();

    const templateName =
        document.getElementById("emailTemplate").options[
            document.getElementById("emailTemplate").selectedIndex
        ].text;

    const candidateId = window.currentCandidateId;
    const attachmentInput = document.getElementById("emailAttachments");
    const attachments = Array.from((attachmentInput && attachmentInput.files) || []);

    if (!to || !subject || !body) {
        showEmailError("Please select a template and make sure To, Subject, and Body are filled.");
        btn.disabled = false;
        btn.innerText = "Send";
        return;
    }
    if (attachments.length > 3) {
        showEmailError("Please attach no more than 3 files.");
        btn.disabled = false;
        btn.innerText = "Send";
        return;
    }
    if (attachments.some(file => file.size > 10 * 1024 * 1024)) {
        showEmailError("Each attachment must be 10 MB or smaller.");
        btn.disabled = false;
        btn.innerText = "Send";
        return;
    }

    try {
        const fd = new FormData();
        fd.append("candidate_id", candidateId || "");
        fd.append("template_name", templateName || "custom");
        fd.append("to", to);
        fd.append("subject", subject);
        fd.append("body", body);
        attachments.forEach(file => fd.append("attachments", file));
        const res = await fetch("/api/send_email", {
            method: "POST",
            body: fd
        });

        const data = await res.json();

        if (data.ok) {
            btn.innerText = "Sent âœ“";
            showToast("Email sent successfully", "success");
            closeEmailModal();
        } else {
            showEmailError(data.error || "Failed to send email");
            btn.disabled = false;
            btn.innerText = "Send";
        }
    } catch (e) {
        console.error(e);
        showEmailError("Unable to send email right now. Please try again.");
        btn.disabled = false;
        btn.innerText = "Send";
    }
}

function closeEmailModal() {
    document.getElementById("emailModal").classList.remove("active");
    const attachmentInput = document.getElementById("emailAttachments");
    if (attachmentInput) attachmentInput.value = "";
    const btn = document.getElementById("sendEmailBtn");
    if (btn) {
      btn.disabled = false;
      btn.innerText = "Send";
    }
}

async function extractJdCriteria() {
  const jd = document.getElementById('jdMatchJd').files[0];
  const jdText = document.getElementById('jdMatchText').value.trim();
  const btn = document.getElementById('jdMatchBtn');
  const alertBox = document.getElementById('jdMatchAlert');
  const result = document.getElementById('jdCriteriaResult');
  alertBox.style.display = 'none';
  if (!jd && !jdText) {
    alertBox.textContent = 'Please upload a JD file or paste JD text.';
    alertBox.style.display = 'block';
    return;
  }
  const fd = new FormData();
  if (jd) fd.append('jd_file', jd);
  if (jdText) fd.append('jd_text', jdText);
  btn.disabled = true;
  btn.textContent = 'Extracting...';
  result.innerHTML = '<div class="muted">Analysing JD...</div>';
  try {
    const res = await fetch('/api/parse_jd', {method:'POST', body:fd});
    const data = await readJsonResponse(res);
    if (!res.ok || data.error) throw new Error(data.error || 'Unable to analyse JD');
    const parsed = data.parsed_jd || data;
    window.currentExtractedJd = parsed;
    window.currentJdText = jdText;
    const interviewText = document.getElementById('interviewJdText');
    if (jdText && interviewText && !interviewText.value.trim()) interviewText.value = jdText;
    const interviewFileName = document.getElementById('interviewJdFileName');
    if (interviewFileName) {
      interviewFileName.textContent = jd ? `Using extracted JD: ${jd.name}` : 'Using extracted JD from pasted text.';
    }
    const questionsPanel = document.getElementById('screeningQuestionsPanel');
    if (questionsPanel) questionsPanel.innerHTML = 'JD analysis is ready for screening question generation.';
    result.innerHTML = renderJdCriteria(parsed);
  } catch(e) {
    alertBox.textContent = e.message;
    alertBox.style.display = 'block';
    result.innerHTML = '<div class="muted">Could not analyse the JD. Please check the JD text and try again.</div>';
  } finally {
    btn.disabled = false;
    btn.textContent = 'Analyse JD';
    updateJdMatchStatus();
  }
}

function renderJdCriteria(jd) {
  const exp = jd.experience_required || {};
  const must = jd.must_have_skills || (jd.must_have_skills_weighted || []).map(item => item.skill).filter(Boolean);
  const nice = jd.nice_to_have_skills || [];
  const education = jd.education_required || [];
  const certs = jd.certifications_required || [];
  const responsibilities = jd.responsibilities || jd.role_responsibilities || [];
  const chips = items => (items && items.length)
    ? items.map(item => `<span class="skill-tag">${escapeHtml(String(item))}</span>`).join('')
    : '<span class="muted">Not found</span>';
  return `
    <div class="screening-question">
      <strong>${escapeHtml(jd.role_title || jd.title || 'Role title not found')}</strong>
      <p>Experience: ${escapeHtml(exp.min_years ? `${exp.min_years}${exp.max_years ? '-' + exp.max_years : '+'} years` : 'Not found')}</p>
      <p>Location: ${escapeHtml(jd.location || 'Not found')} ${jd.employment_type ? ' Â· ' + escapeHtml(jd.employment_type) : ''}</p>
      <p>Domain: ${escapeHtml(jd.domain || 'Not found')}</p>
    </div>
    <div class="screening-question">
      <strong>Role / Responsibilities Summary</strong>
      ${responsibilities.length ? `<ul class="insight-list">${responsibilities.slice(0, 8).map(item => `<li>${escapeHtml(item)}</li>`).join('')}</ul>` : '<p class="muted">No specific responsibilities were found in the JD.</p>'}
    </div>
    <div class="screening-question">
      <strong>Mandatory Tech Skills</strong>
      <div class="card-skills">${chips(must)}</div>
      ${must.length ? '' : '<p class="muted">Mandatory skills were not confidently extracted. Add them manually before using matching rules.</p>'}
    </div>
    <div class="screening-question">
      <strong>Good to Have</strong>
      <div class="card-skills">${chips(nice)}</div>
    </div>
    <div class="screening-question">
      <strong>Education and Certifications</strong>
      <p>Education: ${education.length ? escapeHtml(education.join(', ')) : 'Not found'}</p>
      <p>Certifications: ${certs.length ? escapeHtml(certs.join(', ')) : 'Not found'}</p>
    </div>
    `;
}

async function readJsonResponse(res) {
  const contentType = res.headers.get('content-type') || '';
  if (contentType.includes('application/json')) {
    return await res.json();
  }
  const text = await res.text();
  const plainText = text.replace(/<[^>]*>/g, ' ').replace(/\s+/g, ' ').trim();
  if (res.status === 401 || res.status === 403) {
    throw new Error('Your session may have expired or you do not have access. Please refresh and log in again.');
  }
  if (res.status === 413) {
    throw new Error('Uploaded files are too large. Please reduce the number or size of CVs and try again.');
  }
  if (res.status >= 500) {
    throw new Error('Server error while processing this request. Please check the ATS terminal/logs for details.');
  }
  if (text.toLowerCase().includes('<html')) {
    throw new Error(`Server returned an unexpected page instead of data (${res.status}). Please refresh and try again.`);
  }
  throw new Error(plainText.slice(0, 220) || `Server returned an unexpected response (${res.status}).`);
}

async function generateScreeningQuestions() {
  const panel = document.getElementById('screeningQuestionsPanel');
  const btn = document.getElementById('generateQuestionsBtn');
  const jd = (document.getElementById('interviewJdFile')?.files || [])[0] || (document.getElementById('jdMatchJd')?.files || [])[0];
  const jdText = (document.getElementById('interviewJdText')?.value || document.getElementById('jdMatchText')?.value || window.currentJdText || '').trim();
  if (!jd && !jdText && !window.currentMatchAnalysis && !window.currentExtractedJd) {
    showToast('Upload a JD file or paste JD text first', 'error');
    return;
  }
  panel.innerHTML = '<div class="muted">Generating questions...</div>';
  if (btn) {
    btn.disabled = true;
    btn.style.opacity = '0.55';
    btn.textContent = 'Generating...';
  }
  try {
    const fd = new FormData();
    if (jd) fd.append('jd_file', jd);
    if (jdText) fd.append('jd_text', jdText);
    if (window.currentExtractedJd) fd.append('analysis_json', JSON.stringify({parsed_jd: window.currentExtractedJd}));
    if (window.currentMatchAnalysis) fd.append('analysis_json', JSON.stringify(window.currentMatchAnalysis));
    const res = await fetch('/api/match/screening_questions', {method: 'POST', body: fd});
    const data = await readJsonResponse(res);
    if (!res.ok || data.error) throw new Error(data.error || 'Unable to generate questions');
    const questions = Array.isArray(data.questions) ? data.questions : [];
    window.currentScreeningQuestions = questions;
    window.currentScreeningQuestionMeta = {skills: data.skills || [], note: data.note || ''};
    panel.innerHTML = questions.length ? `${questions.length} questions generated. They opened in a separate window.` : 'No questions generated.';
    openScreeningQuestionsModal(questions, data.note || '');
  } catch(e) {
    panel.innerHTML = `<div class="muted">${escapeHtml(e.message)}</div>`;
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.style.opacity = '1';
      btn.textContent = 'Generate Questions';
    }
  }
}

function renderScreeningQuestions(questions, note='') {
  const arr = Array.isArray(questions) ? questions : [];
  const noteHtml = note ? `<div class="muted" style="margin-bottom:12px">${escapeHtml(note)}</div>` : '';
  return noteHtml + (arr.length ? arr.map((q, i) => `
    <div class="screening-question">
      <strong>${i + 1}. ${escapeHtml(q.skill || 'Screening question')}</strong>
      <p>${escapeHtml(q.question || '')}</p>
      <em>Good answer signal: ${escapeHtml(q.expected_signal || '-')}</em>
      <em>Follow-up: ${escapeHtml(q.follow_up || '-')}</em>
    </div>
  `).join('') : '<div class="muted">No questions generated.</div>');
}

function openScreeningQuestionsModal(questions, note='') {
  document.getElementById('screeningQuestionsModalContent').innerHTML = renderScreeningQuestions(questions, note);
  document.getElementById('screeningQuestionsModal').classList.add('active');
}

function updateResumeAnalysisFileName() {
  const file = (document.getElementById('resumeAnalysisFile')?.files || [])[0];
  const el = document.getElementById('resumeAnalysisFileName');
  const status = document.getElementById('resumeAnalysisStatus');
  if (el) el.textContent = file ? `Uploaded resume: ${file.name}` : 'No resume uploaded.';
  if (status) status.textContent = file ? 'Resume loaded Â· Ready to analyze' : 'Ready to analyze resume';
}

async function loadResumeDefaultPrompt() {
  const promptEl = document.getElementById('resumeCustomPrompt');
  if (!promptEl || promptEl.value.trim()) return;
  try {
    const res = await fetch('/api/candidate_resume/default_prompt');
    const data = await res.json();
    if (data.prompt) promptEl.value = data.prompt;
  } catch(e) {
    console.error('Unable to load resume default prompt', e);
  }
}

async function analyzeCandidateResume() {
  const file = (document.getElementById('resumeAnalysisFile')?.files || [])[0];
  const btn = document.getElementById('resumeAnalyzeBtn');
  const alertBox = document.getElementById('resumeAnalysisAlert');
  const sectionsEl = document.getElementById('resumeSectionsResult');
  const summaryEl = document.getElementById('resumeSummaryResult');
  const skillCheckEl = document.getElementById('resumeSkillCheckResult');
  if (alertBox) alertBox.style.display = 'none';
  if (!file) {
    alertBox.textContent = 'Please upload a resume file.';
    alertBox.style.display = 'block';
    return;
  }
  const fd = new FormData();
  fd.append('resume_file', file);
  fd.append('skills_to_check', document.getElementById('resumeSkillCheckInput')?.value || '');
  fd.append('custom_prompt', document.getElementById('resumeCustomPrompt')?.value || '');
  btn.disabled = true;
  btn.style.opacity = '0.55';
  btn.textContent = 'Analyzing...';
  sectionsEl.innerHTML = '<div class="muted">Extracting resume sections...</div>';
  summaryEl.innerHTML = '<div class="muted">Generating candidate summary...</div>';
  if (skillCheckEl) skillCheckEl.innerHTML = '';
  try {
    const res = await fetch('/api/candidate_resume/analyze', {method: 'POST', body: fd});
    const data = await readJsonResponse(res);
    if (!res.ok || data.error) throw new Error(data.error || 'Unable to analyze resume');
    sectionsEl.innerHTML = renderResumeSections(data.sections || {});
    if (skillCheckEl) skillCheckEl.innerHTML = renderSkillCheckResult(data.skill_check || {});
    summaryEl.innerHTML = renderResumeSummary(data.summary || {});
    document.getElementById('resumeAnalysisStatus').textContent = 'Resume analysis complete';
  } catch(e) {
    alertBox.textContent = e.message;
    alertBox.style.display = 'block';
    sectionsEl.innerHTML = 'Resume sections could not be extracted.';
    summaryEl.innerHTML = 'Candidate summary could not be generated.';
  } finally {
    btn.disabled = false;
    btn.style.opacity = '1';
    btn.textContent = 'Analyze Resume';
  }
}

function renderSkillCheckResult(result) {
  const checked = result.checked_skills || [];
  if (!checked.length) return '';
  const found = result.found || [];
  const missing = result.missing || [];
  return `
    <div class="screening-question">
      <strong>Skill Check</strong>
      <p>Mentioned in CV: ${found.length ? escapeHtml(found.join(', ')) : 'None of the entered skills were found.'}</p>
      <p>Not clearly mentioned: ${missing.length ? escapeHtml(missing.join(', ')) : 'None'}</p>
    </div>`;
}

function renderResumeSections(sections) {
  const entries = Object.entries(sections || {}).filter(([_, value]) => String(value || '').trim());
  if (!entries.length) return '<div class="muted">No clear resume sections were detected.</div>';
  return entries.map(([label, value]) => `
    <div class="screening-question">
      <strong>${escapeHtml(label.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase()))}</strong>
      <p>${escapeHtml(String(value)).replace(/\n/g, '<br>')}</p>
    </div>
  `).join('');
}

function listItems(items, fallback='Not found') {
  if (!Array.isArray(items) || !items.length) return `<p>${fallback}</p>`;
  return `<ul class="insight-list">${items.map(item => `<li>${escapeHtml(typeof item === 'string' ? item : JSON.stringify(item))}</li>`).join('')}</ul>`;
}

function renderResumeSummary(summary) {
  const contact = summary.contact_details || {};
  const orgs = summary.organization_experience || [];
  const skills = summary.technical_skills || [];
  return `
    <div class="screening-question">
      <strong>${escapeHtml(summary.candidate_name || 'Candidate')}</strong>
      <p>Total Experience: ${escapeHtml(summary.total_experience || 'Not found')}</p>
      <p>Current Role: ${escapeHtml(summary.current_role || 'Not found')}</p>
      <p>Current Company: ${escapeHtml(summary.current_company || 'Not found')}</p>
      <p>Current Location: ${escapeHtml(summary.current_location || 'Not found')}</p>
    </div>
    <div class="screening-question">
      <strong>Contact Details</strong>
      <p>Email: ${escapeHtml(contact.email || 'Not found')}</p>
      <p>Phone: ${escapeHtml(contact.phone || 'Not found')}</p>
      <p>LinkedIn: ${escapeHtml(contact.linkedin || 'Not found')}</p>
    </div>
    <div class="screening-question">
      <strong>Experience by Organization</strong>
      ${listItems(orgs.map(item => `${item.company || '-'} Â· ${item.role || '-'} Â· ${item.duration || '-'} Â· ${item.summary || ''}`))}
    </div>
    <div class="screening-question">
      <strong>Technical Skills</strong>
      ${listItems(skills.map(item => `${item.skill || '-'} Â· ${item.experience || 'Experience not clear'} Â· ${item.evidence || ''}`))}
    </div>
    <div class="screening-question">
      <strong>Education</strong>
      ${listItems(summary.education_details || [])}
    </div>`;
}

function clearResumeAnalysis() {
  const file = document.getElementById('resumeAnalysisFile');
  if (file) file.value = '';
  document.getElementById('resumeSectionsResult').innerHTML = 'Upload a resume to see labelled sections.';
  document.getElementById('resumeSummaryResult').innerHTML = 'Candidate summary will appear after analysis.';
  document.getElementById('resumeSkillCheckResult').innerHTML = '';
  const skillInput = document.getElementById('resumeSkillCheckInput');
  if (skillInput) skillInput.value = '';
  const customPrompt = document.getElementById('resumeCustomPrompt');
  if (customPrompt) customPrompt.value = '';
  loadResumeDefaultPrompt();
  const alertBox = document.getElementById('resumeAnalysisAlert');
  if (alertBox) alertBox.style.display = 'none';
  updateResumeAnalysisFileName();
}

async function exportScreeningQuestionsPdf() {
  const questions = window.currentScreeningQuestions || [];
  if (!questions.length) return showToast('Generate questions first', 'error');
  try {
    const res = await fetch('/api/match/screening_questions_pdf', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({questions, meta: window.currentScreeningQuestionMeta || {}})
    });
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      throw new Error(data.error || 'Unable to export PDF');
    }
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `interview_screening_questions_${new Date().toISOString().slice(0,10)}.pdf`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
    showToast('Screening questions PDF exported', 'success');
  } catch(e) {
    showToast(e.message, 'error');
  }
}

function switchJdMode(mode) {
  document.querySelectorAll('.jd-mode-tab').forEach(btn => btn.classList.remove('active'));
  document.querySelectorAll('.jd-mode-panel').forEach(panel => panel.classList.remove('active'));
  const match = mode === 'match';
  document.querySelectorAll('.jd-mode-tab')[match ? 0 : 1]?.classList.add('active');
  document.getElementById(match ? 'jdModeMatch' : 'jdModeInterview').classList.add('active');
  if (!match && window.currentExtractedJd) {
    const panel = document.getElementById('screeningQuestionsPanel');
    if (panel && panel.textContent.includes('Questions will open')) {
      panel.innerHTML = 'JD analysis is ready for screening question generation.';
    }
  }
}

function updateJdMatchStatus() {
  const jdText = (document.getElementById('jdMatchText') || {}).value || '';
  const jdFile = (document.getElementById('jdMatchJd')?.files || [])[0];
  const wordCount = jdText.trim() ? jdText.trim().split(/\s+/).length : 0;
  const wordEl = document.getElementById('jdMatchWordCount');
  const statusEl = document.getElementById('jdMatchStatus');
  const jdFileName = document.getElementById('jdMatchJdFileName');
  if (wordEl) wordEl.textContent = `${wordCount} word${wordCount === 1 ? '' : 's'}`;
  if (statusEl) statusEl.textContent = jdFile || wordCount ? 'JD loaded Â· Ready to analyse' : 'Ready to analyse JD';
  if (jdFileName) jdFileName.textContent = jdFile ? `Uploaded JD: ${jdFile.name}` : 'No JD file uploaded.';
}

function updateInterviewJdFileName() {
  const jdFile = (document.getElementById('interviewJdFile')?.files || [])[0];
  const el = document.getElementById('interviewJdFileName');
  if (el) el.textContent = jdFile ? `Uploaded JD: ${jdFile.name}` : 'No JD file uploaded.';
}

function splitJdReviewList(value) {
  return String(value || '')
    .split(/[\n,;|]+/)
    .map(item => item.trim())
    .filter(Boolean);
}

function syncJdCvReviewedDraft() {
  if (!window.currentExtractedJd) return null;
  const panel = document.getElementById('jdCvReviewPanel');
  if (!panel || !panel.classList.contains('active')) return window.currentReviewedJd || null;
  const base = JSON.parse(JSON.stringify(window.currentExtractedJd));
  const title = (document.getElementById('jdReviewRoleTitle')?.value || '').trim();
  const roleFamily = (document.getElementById('jdReviewRoleFamily')?.value || '').trim();
  const domain = (document.getElementById('jdReviewDomain')?.value || '').trim();
  const minExp = (document.getElementById('jdReviewMinExp')?.value || '').trim();
  const maxExp = (document.getElementById('jdReviewMaxExp')?.value || '').trim();
  const location = (document.getElementById('jdReviewLocation')?.value || '').trim();
  const industry = (document.getElementById('jdReviewIndustry')?.value || '').trim();
  const adjacentIndustries = splitJdReviewList(document.getElementById('jdReviewAdjacentIndustries')?.value || '');
  const industryStrictness = (document.getElementById('jdReviewIndustryStrictness')?.value || 'preferred').trim();
  const industryNotes = (document.getElementById('jdReviewIndustryNotes')?.value || '').trim();
  const mustHave = splitJdReviewList(document.getElementById('jdReviewMustHave')?.value || '');
  const niceToHave = splitJdReviewList(document.getElementById('jdReviewNiceToHave')?.value || '');
  const responsibilities = splitJdReviewList((document.getElementById('jdReviewResponsibilities')?.value || '').replace(/\r/g, '\n'));
  const education = splitJdReviewList(document.getElementById('jdReviewEducation')?.value || '');
  const certifications = splitJdReviewList(document.getElementById('jdReviewCertifications')?.value || '');
  const relaxExpMin = (document.getElementById('jdReviewRelaxExpMin')?.value || '').trim();
  const relaxSkills = splitJdReviewList(document.getElementById('jdReviewRelaxSkills')?.value || '');
  const relaxLocation = (document.getElementById('jdReviewRelaxLocation')?.value || '').trim();
  const relaxNotice = (document.getElementById('jdReviewRelaxNotice')?.value || '').trim();
  const relaxOther = (document.getElementById('jdReviewRelaxOther')?.value || '').trim();
  const nonNegotiables = splitJdReviewList(document.getElementById('jdReviewNonNegotiables')?.value || '');
  const reviewNotes = (document.getElementById('jdReviewNotes')?.value || '').trim();
  const reviewed = {
    ...base,
    title: title,
    role_title: title,
    role_family: roleFamily || base.role_family || '',
    domain: domain || base.domain || '',
    location: location || base.location || '',
    industry_context: {
      industry: industry || base.industry_context?.industry || base.industry || '',
      adjacent_industries: adjacentIndustries,
      strictness: industryStrictness,
      notes: industryNotes,
      examples: industry ? [
        `Industry context: ${industry}`,
        adjacentIndustries.length ? `Adjacent industries allowed: ${adjacentIndustries.join(', ')}` : '',
        industryStrictness ? `Industry rule: ${industryStrictness}` : ''
      ].filter(Boolean) : []
    },
    recruiter_relaxations: {
      experience_min_years: relaxExpMin ? Number(relaxExpMin) : Number((base.experience_required || {}).min_years || 0),
      skills_relaxed: relaxSkills,
      location: relaxLocation,
      notice_period: relaxNotice,
      other: relaxOther,
      non_negotiables: nonNegotiables
    },
    must_have_skills: mustHave,
    nice_to_have_skills: niceToHave,
    responsibilities: responsibilities,
    role_responsibilities: responsibilities,
    education_required: education,
    certifications_required: certifications,
    review_notes: reviewNotes,
    parse_source: 'recruiter_reviewed',
    parser_confidence: 'reviewed',
    experience_required: {
      min_years: minExp ? Number(minExp) : Number((base.experience_required || {}).min_years || 0),
      max_years: maxExp ? Number(maxExp) : Number((base.experience_required || {}).max_years || 0)
    },
    screening_context: {
      industry: industry || base.industry_context?.industry || base.industry || '',
      adjacent_industries: adjacentIndustries,
      strictness: industryStrictness,
      relaxations: {
        experience_min_years: relaxExpMin ? Number(relaxExpMin) : Number((base.experience_required || {}).min_years || 0),
        skills_relaxed: relaxSkills,
        location: relaxLocation,
        notice_period: relaxNotice,
        other: relaxOther,
        non_negotiables: nonNegotiables
      }
    }
  };
  window.currentReviewedJd = reviewed;
  const reviewState = document.getElementById('jdCvReviewState');
  if (reviewState) reviewState.textContent = 'Reviewed JD ready for matching';
  const badge = document.getElementById('jdCvReviewBadge');
  if (badge) badge.textContent = 'Reviewed';
  const status = document.getElementById('jdCvMatchStatus');
  if (status) status.textContent = 'JD reviewed · Ready to match';
  return reviewed;
}

function renderJdReviewPanel(parsed) {
  const panel = document.getElementById('jdCvReviewPanel');
  if (!panel) return;
  const exp = parsed?.experience_required || {};
  const warnings = Array.isArray(parsed?.parser_warnings) ? parsed.parser_warnings : [];
  const reasons = Array.isArray(parsed?.manual_review_reasons) ? parsed.manual_review_reasons : [];
  const relax = parsed?.recruiter_relaxations || {};
  const industryContext = parsed?.industry_context || {};
  const listText = items => Array.isArray(items) ? items.filter(Boolean).join(', ') : (typeof items === 'string' ? items : '');
  const lineText = items => Array.isArray(items) ? items.filter(Boolean).join('\n') : (typeof items === 'string' ? items : '');
  panel.innerHTML = `
    <div class="jd-review-head">
      <div>
        <h3>Parsed JD Review</h3>
        <p>Confirm the extracted fields before matching. Add the industry context, then mark what the recruiter says is flexible so AI screening can judge the candidate the same way a recruiter would.</p>
      </div>
      <div class="jd-review-badge" id="jdCvReviewBadge">${escapeHtml(String(parsed?.parser_confidence || 'review'))}</div>
    </div>
    <div class="jd-review-note">
      <strong>How to use this panel</strong>
      <div>1. Enter the real industry for the role, such as Decorative Paints, Tool Room, Cloud Infrastructure, or Banking.</div>
      <div>2. Mark whether that industry is required, preferred, or flexible, and list any adjacent industries the client accepts.</div>
      <div>3. Add the relaxations the recruiter confirmed, like lower experience, flexible location, or skills that should be treated as preferred instead of mandatory.</div>
    </div>
    <div class="jd-review-grid">
      <div class="form-group field-span-2">
        <label>Role Title</label>
        <input id="jdReviewRoleTitle" value="${escapeHtml(parsed?.role_title || parsed?.title || '')}" oninput="syncJdCvReviewedDraft()">
      </div>
      <div class="form-group">
        <label>Role Family</label>
        <input id="jdReviewRoleFamily" value="${escapeHtml(parsed?.role_family || '')}" oninput="syncJdCvReviewedDraft()">
      </div>
      <div class="form-group">
        <label>Domain</label>
        <input id="jdReviewDomain" value="${escapeHtml(parsed?.domain || '')}" oninput="syncJdCvReviewedDraft()">
      </div>
      <div class="form-group">
        <label>Min Experience</label>
        <input id="jdReviewMinExp" type="number" min="0" step="0.5" value="${escapeHtml(exp.min_years ?? '')}" oninput="syncJdCvReviewedDraft()">
      </div>
      <div class="form-group">
        <label>Max Experience</label>
        <input id="jdReviewMaxExp" type="number" min="0" step="0.5" value="${escapeHtml(exp.max_years ?? '')}" oninput="syncJdCvReviewedDraft()">
      </div>
      <div class="form-group field-span-2">
        <label>Location</label>
        <input id="jdReviewLocation" value="${escapeHtml(parsed?.location || '')}" oninput="syncJdCvReviewedDraft()">
      </div>
      <div class="form-group">
        <label>Target Industry / Work Context</label>
        <input id="jdReviewIndustry" value="${escapeHtml(industryContext.industry || parsed?.industry || parsed?.domain || '')}" placeholder="Decorative Paints, Tool Room, Cloud Infrastructure" oninput="syncJdCvReviewedDraft()">
        <small class="muted">Example: Decorative Paints, Tool Room Manufacturing, Banking, Cloud Infrastructure.</small>
      </div>
      <div class="form-group">
        <label>Industry Rule</label>
        <select id="jdReviewIndustryStrictness" onchange="syncJdCvReviewedDraft()">
          <option value="required" ${String(industryContext.strictness || 'preferred') === 'required' ? 'selected' : ''}>Required</option>
          <option value="preferred" ${String(industryContext.strictness || 'preferred') === 'preferred' ? 'selected' : ''}>Preferred</option>
          <option value="flexible" ${String(industryContext.strictness || 'preferred') === 'flexible' ? 'selected' : ''}>Flexible</option>
        </select>
        <small class="muted">Use Preferred when adjacent industries are acceptable, but same-industry profiles should rank higher.</small>
      </div>
      <div class="form-group field-span-2">
        <label>Adjacent Industries Allowed</label>
        <textarea id="jdReviewAdjacentIndustries" rows="3" placeholder="Building Materials, Construction Chemicals, FMCG" oninput="syncJdCvReviewedDraft()">${escapeHtml(listText(industryContext.adjacent_industries || []))}</textarea>
        <small class="muted">Example: Building Materials, Construction Chemicals, FMCG, Automotive, SaaS.</small>
      </div>
      <div class="form-group field-span-2">
        <label>Industry Notes</label>
        <textarea id="jdReviewIndustryNotes" rows="2" placeholder="Tell Gemini what background matters and what can be treated as adjacent." oninput="syncJdCvReviewedDraft()">${escapeHtml(industryContext.notes || '')}</textarea>
        <small class="muted">Example: “Paints preferred, building materials and construction chemicals acceptable as adjacent backgrounds.”</small>
      </div>
      <div class="form-group field-span-2">
        <label>Must-have Skills</label>
        <textarea id="jdReviewMustHave" rows="3" oninput="syncJdCvReviewedDraft()">${escapeHtml(listText(parsed?.must_have_skills || (parsed?.must_have_skills_weighted || []).map(item => item.skill).filter(Boolean)))}</textarea>
      </div>
      <div class="form-group field-span-2">
        <label>Nice-to-have Skills</label>
        <textarea id="jdReviewNiceToHave" rows="3" oninput="syncJdCvReviewedDraft()">${escapeHtml(listText(parsed?.nice_to_have_skills || []))}</textarea>
      </div>
      <div class="form-group field-span-2">
        <label>Responsibilities / Evidence</label>
        <textarea id="jdReviewResponsibilities" rows="4" oninput="syncJdCvReviewedDraft()">${escapeHtml(lineText(parsed?.responsibilities || parsed?.role_responsibilities || []))}</textarea>
      </div>
      <div class="form-group">
        <label>Education</label>
        <textarea id="jdReviewEducation" rows="3" oninput="syncJdCvReviewedDraft()">${escapeHtml(listText(parsed?.education_required || []))}</textarea>
      </div>
      <div class="form-group">
        <label>Certifications</label>
        <textarea id="jdReviewCertifications" rows="3" oninput="syncJdCvReviewedDraft()">${escapeHtml(listText(parsed?.certifications_required || []))}</textarea>
      </div>
      <div class="form-group field-span-2">
        <label>Recruiter-Approved Experience Floor</label>
        <input id="jdReviewRelaxExpMin" type="number" min="0" step="0.5" value="${escapeHtml(relax.experience_min_years ?? exp.min_years ?? '')}" placeholder="3">
        <small class="muted">Example: original JD says 5+ years, but the recruiter confirms 3+ years is acceptable.</small>
      </div>
      <div class="form-group field-span-2">
        <label>Skills That Can Be Treated as Preferred</label>
        <textarea id="jdReviewRelaxSkills" rows="2" placeholder="Optional skills that should not block the candidate" oninput="syncJdCvReviewedDraft()">${escapeHtml(listText(relax.skills_relaxed || []))}</textarea>
        <small class="muted">Example: SAP MM, one reporting tool, one cloud service, or one paint-product category can be treated as preferred, not mandatory.</small>
      </div>
      <div class="form-group">
        <label>Location Relaxation</label>
        <input id="jdReviewRelaxLocation" value="${escapeHtml(relax.location || '')}" placeholder="Location can be flexible / Remote / Relocation okay" oninput="syncJdCvReviewedDraft()">
        <small class="muted">Example: “Location flexible within West Zone” or “Remote okay”.</small>
      </div>
      <div class="form-group">
        <label>Notice Period Relaxation</label>
        <input id="jdReviewRelaxNotice" value="${escapeHtml(relax.notice_period || '')}" placeholder="Notice period can be up to 60 days" oninput="syncJdCvReviewedDraft()">
        <small class="muted">Example: “Notice up to 60 days is acceptable” or “Immediate joiners preferred”.</small>
      </div>
      <div class="form-group field-span-2">
        <label>Non-negotiables / Hard No</label>
        <textarea id="jdReviewNonNegotiables" rows="2" placeholder="What must still be treated as mandatory?" oninput="syncJdCvReviewedDraft()">${escapeHtml(listText(relax.non_negotiables || []))}</textarea>
        <small class="muted">Example: dealer sales only, no project sales, local language required, safety certification required.</small>
      </div>
      <div class="form-group field-span-2">
        <label>Other Relaxations / Notes</label>
        <textarea id="jdReviewRelaxOther" rows="2" placeholder="Any other recruiter notes for AI screening" oninput="syncJdCvReviewedDraft()">${escapeHtml(relax.other || '')}</textarea>
      </div>
      <div class="form-group field-span-2">
        <label>Recruiter Notes</label>
        <textarea id="jdReviewNotes" rows="3" placeholder="Optional notes for this match run" oninput="syncJdCvReviewedDraft()">${escapeHtml(parsed?.review_notes || '')}</textarea>
      </div>
    </div>
    ${warnings.length || reasons.length ? `
      <div class="jd-review-note">
        <strong>Parser Guidance</strong>
        ${warnings.length ? `<div>Warnings: ${escapeHtml(warnings.join(' · '))}</div>` : ''}
        ${reasons.length ? `<div>Manual review reasons: ${escapeHtml(reasons.join(' · '))}</div>` : ''}
      </div>
    ` : ''}
  `;
  panel.classList.add('active');
  syncJdCvReviewedDraft();
}

async function reviewJdForMatch() {
  const jdFile = (document.getElementById('jdCvMatchJdFile')?.files || [])[0];
  const jdText = (document.getElementById('jdCvMatchText')?.value || '').trim();
  const alertBox = document.getElementById('jdCvMatchAlert');
  const reviewState = document.getElementById('jdCvReviewState');
  if (alertBox) alertBox.style.display = 'none';
  if (!jdFile && !jdText) {
    if (alertBox) { alertBox.textContent = 'Upload a JD file or paste JD text first.'; alertBox.style.display = 'block'; }
    return;
  }
  const fd = new FormData();
  if (jdFile) fd.append('jd_file', jdFile);
  if (jdText) fd.append('jd_text', jdText);
  const btn = document.getElementById('jdCvReviewBtn');
  if (btn) { btn.disabled = true; btn.textContent = 'Parsing...'; }
  if (reviewState) reviewState.textContent = 'Parsing JD for recruiter review...';
  try {
    const res = await fetch('/api/parse_jd', {method:'POST', body:fd});
    const data = await readJsonResponse(res);
    if (!res.ok || data.error) throw new Error(data.error || 'Unable to parse JD');
    const parsed = data.parsed_jd || data;
    window.currentExtractedJd = parsed;
    renderJdReviewPanel(parsed);
    window.skipJdReviewInvalidation = true;
    updateJdCvMatchFiles();
    window.skipJdReviewInvalidation = false;
    showToast('JD parsed for review', 'success');
  } catch(e) {
    if (alertBox) { alertBox.textContent = e.message; alertBox.style.display = 'block'; }
    if (reviewState) reviewState.textContent = 'JD review could not be loaded';
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = 'Parse & Review JD'; }
  }
}

function updateJdCvMatchFiles() {
  const jdFile = (document.getElementById('jdCvMatchJdFile')?.files || [])[0];
  const cvFiles = Array.from(document.getElementById('jdCvMatchCvFiles')?.files || []);
  const jdName = document.getElementById('jdCvMatchJdName');
  const cvNames = document.getElementById('jdCvMatchCvNames');
  const summary = document.getElementById('jdCvMatchFileSummary');
  const status = document.getElementById('jdCvMatchStatus');
  const jdSignature = jdFile ? `file:${jdFile.name}:${jdFile.size || 0}` : '';
  const jdChanged = jdSignature !== (window.currentJdMatchSignature || '');
  if (jdChanged) {
    window.currentExtractedJd = null;
    window.currentReviewedJd = null;
  }
  window.currentJdMatchSignature = jdSignature;
  if (jdName) jdName.textContent = jdFile ? `Uploaded JD: ${jdFile.name}` : 'No JD file uploaded.';
  if (cvNames) cvNames.textContent = cvFiles.length ? cvFiles.map(f => f.name).join(', ') : 'No CV files uploaded.';
  if (summary) summary.textContent = `${cvFiles.length} CV${cvFiles.length === 1 ? '' : 's'} selected`;
  if (status) status.textContent = jdFile ? 'JD loaded · ready to match' : 'Ready to match';
}

function clearJdCvBatchMatch() {
  ['jdCvMatchJdFile','jdCvMatchCvFiles'].forEach(id => { const el = document.getElementById(id); if (el) el.value = ''; });
  window.currentExtractedJd = null;
  window.currentReviewedJd = null;
  window.currentJdMatchSignature = '';
  window.currentBatchMatches = [];
  window.currentMatchAnalysis = null;
  const result = document.getElementById('jdMatchResult');
  if (result) { result.innerHTML = ''; result.style.display = 'none'; }
  const ranking = document.getElementById('jdMatchRanking');
  if (ranking) { ranking.classList.add('empty'); ranking.innerHTML = 'Run a match to see candidate ranking.'; }
  const stats = document.getElementById('jdMatchBatchStats');
  if (stats) stats.innerHTML = '';
  const alertBox = document.getElementById('jdCvMatchAlert');
  if (alertBox) alertBox.style.display = 'none';
  updateJdCvMatchFiles();
}

  async function resetJdCvMatchCache() {
    const status = document.getElementById('jdCvMatchStatus');
    const alertBox = document.getElementById('jdCvMatchAlert');
    if (!confirm('Reset cached JD/CV match data for this version? This will clear cached parsed JD, cached parsed CVs, and saved match results.')) return;
    try {
      const res = await fetch('/api/jd_match/cache/reset', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ scope: 'matching' })
      });
      const data = await readJsonResponse(res);
      if (!res.ok || data.error) throw new Error(data.error || 'Unable to reset match cache');
      window.currentBatchMatches = [];
      window.currentMatchAnalysis = null;
      const ranking = document.getElementById('jdMatchRanking');
      if (ranking) {
        ranking.classList.add('empty');
        ranking.innerHTML = 'Cache cleared. Run the match again to rebuild results.';
      }
      const stats = document.getElementById('jdMatchBatchStats');
      if (stats) stats.innerHTML = '';
      const result = document.getElementById('jdMatchResult');
      if (result) { result.innerHTML = ''; result.style.display = 'none'; }
      if (status) status.textContent = 'Cache cleared. Ready to match again.';
      if (alertBox) { alertBox.style.display = 'none'; alertBox.textContent = ''; }
      showToast('Match cache cleared', 'success');
    } catch (e) {
      showToast(e.message, 'error');
      if (alertBox) {
        alertBox.textContent = e.message;
        alertBox.style.display = 'block';
      }
      if (status) status.textContent = 'Cache reset failed';
    }
  }

async function runJdCvBatchMatch() {
  const jdFile = (document.getElementById('jdCvMatchJdFile')?.files || [])[0];
  const cvFiles = Array.from(document.getElementById('jdCvMatchCvFiles')?.files || []);
  const alertBox = document.getElementById('jdCvMatchAlert');
  const btn = document.getElementById('jdCvRunBtn');
  const status = document.getElementById('jdCvMatchStatus');
  if (alertBox) alertBox.style.display = 'none';
  if (!jdFile) {
    if (alertBox) { alertBox.textContent = 'Upload a JD file first.'; alertBox.style.display = 'block'; }
    return;
  }
  if (!cvFiles.length) {
    if (alertBox) { alertBox.textContent = 'Upload at least one CV file.'; alertBox.style.display = 'block'; }
    return;
  }
  const fd = new FormData();
  if (jdFile) fd.append('jd_file', jdFile);
  cvFiles.forEach(file => fd.append('cv_files', file));
  if (window.currentReviewedJd) {
    fd.append('reviewed_jd_json', JSON.stringify(window.currentReviewedJd));
  } else if (window.currentExtractedJd) {
    fd.append('parsed_jd_json', JSON.stringify(window.currentExtractedJd));
  }
  if (btn) { btn.disabled = true; btn.textContent = 'Matching...'; }
  if (status) status.textContent = `Matching ${cvFiles.length} CV${cvFiles.length === 1 ? '' : 's'}...`;
  const ranking = document.getElementById('jdMatchRanking');
  if (ranking) { ranking.classList.add('empty'); ranking.innerHTML = 'Matching candidates...'; }
  try {
    const res = await fetch('/api/jd_match', {method:'POST', body:fd});
    const data = await readJsonResponse(res);
    if (!res.ok || data.error) throw new Error(data.error || 'Unable to run match');
    const results = data.batch ? (data.results || []) : [data];
    renderBatchRanking(results);
    if (results.length) selectBatchCandidate(0);
    if (data.errors && data.errors.length && alertBox) {
      alertBox.textContent = `${data.errors.length} CV file(s) could not be read. Readable files were ranked.`;
      alertBox.style.display = 'block';
    }
    if (status) status.textContent = `Matched ${results.length} candidate${results.length === 1 ? '' : 's'}`;
  } catch(e) {
    if (alertBox) { alertBox.textContent = e.message; alertBox.style.display = 'block'; }
    if (ranking) ranking.innerHTML = 'Match failed. Check files and try again.';
    if (status) status.textContent = 'Match failed';
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = 'Run Match'; }
  }
}

function renderBatchRanking(results) {
  const ranking = document.getElementById('jdMatchRanking');
  const stats = document.getElementById('jdMatchBatchStats');
  const sorted = [...(results || [])].sort((a,b) => Number(b.final_score || b.score || 0) - Number(a.final_score || a.score || 0));
  window.currentBatchMatches = sorted.map((item, index) => ({...item, match_rank: index + 1, match_pool_size: sorted.length}));
  if (!ranking) return;
  if (!window.currentBatchMatches.length) {
    if (stats) stats.innerHTML = '';
    ranking.classList.add('empty');
    ranking.innerHTML = 'No readable candidate results were generated.';
    return;
  }
  if (stats) {
    const strong = window.currentBatchMatches.filter(item => Number(item.final_score || item.score || 0) >= 80).length;
    const moderate = window.currentBatchMatches.filter(item => Number(item.final_score || item.score || 0) >= 65 && Number(item.final_score || item.score || 0) < 80).length;
    stats.innerHTML = `
      <div class="batch-stat"><strong>${window.currentBatchMatches.length}</strong><span>Total</span></div>
      <div class="batch-stat"><strong>${strong}</strong><span>Strong</span></div>
      <div class="batch-stat"><strong>${moderate}</strong><span>Moderate</span></div>`;
  }
  ranking.classList.remove('empty');
  ranking.innerHTML = window.currentBatchMatches.map((item, index) => {
    const dashboard = item.dashboard || buildDashboardFallback(item);
    const snapshot = dashboard.candidate_snapshot || {};
    const name = snapshot.candidate_name || item.candidate_name || item.cv_filename || `Candidate ${index + 1}`;
    const role = snapshot.current_role || item.cv_filename || 'Role not found';
    const score = Number(item.final_score || item.score || 0);
    return `
      <button class="ranking-item ${index === 0 ? 'active' : ''}" type="button" onclick="selectBatchCandidate(${index})">
        <span class="rank-num">${index + 1}</span>
        <span>
          <span class="rank-name">${escapeHtml(name)}</span>
          <span class="rank-meta">${escapeHtml(role)} Â· ${escapeHtml((dashboard.overview || {}).verdict || item.verdict || '')}</span>
        </span>
        <span class="rank-score" style="color:${scoreColor(score)}">${score}%</span>
      </button>`;
  }).join('');
}

function selectBatchCandidate(index) {
  const item = (window.currentBatchMatches || [])[index];
  if (!item) return;
  window.currentMatchAnalysis = item;
  const panel = document.getElementById('screeningQuestionsPanel');
  if (panel) panel.innerHTML = 'No questions yet.';
  document.querySelectorAll('#jdMatchRanking .ranking-item').forEach((el, i) => el.classList.toggle('active', i === index));
  const result = document.getElementById('jdMatchResult');
  if (!result) return;
  result.innerHTML = renderMatchDashboard(item);
  result.style.display = 'block';
}

function sortBatchMatches() {
  const matches = [...(window.currentBatchMatches || [])];
  if (!matches.length) return;
  matches.sort((a,b) => Number(b.final_score || b.score || 0) - Number(a.final_score || a.score || 0));
  window.currentBatchMatches = matches;
  renderBatchRanking(matches);
  selectBatchCandidate(0);
}

function batchSummaryText() {
  const matches = window.currentBatchMatches || [];
  if (!matches.length) return '';
  return matches.map((item, index) => {
    const dashboard = item.dashboard || buildDashboardFallback(item);
    const snapshot = dashboard.candidate_snapshot || {};
    const overview = dashboard.overview || {};
    const name = snapshot.candidate_name || item.cv_filename || `Candidate ${index + 1}`;
    return `${index + 1}. ${name}: ${overview.final_score || item.final_score || item.score || 0}% - ${overview.verdict || item.verdict || ''}. ${overview.recommendation || ''}`;
  }).join('\n');
}

function copyBatchSummary() {
  const text = batchSummaryText();
  if (!text) return showToast('Run match analysis first', 'error');
  navigator.clipboard.writeText(text);
  showToast('Candidate ranking summary copied', 'success');
}

function buildCsvValue(value) {
  const text = Array.isArray(value) ? value.join('; ') : String(value ?? '');
  return `"${text.replace(/"/g, '""')}"`;
}

function downloadBatchSummaryCsv() {
  const matches = window.currentBatchMatches || [];
  if (!matches.length) return showToast('Run match analysis first', 'error');
  const rows = matches.map((item, index) => {
    const dashboard = item.dashboard || buildDashboardFallback(item);
    const overview = dashboard.overview || {};
    const snapshot = dashboard.candidate_snapshot || {};
    return {
      rank: item.match_rank || index + 1,
      candidate: snapshot.candidate_name || item.candidate_name || item.cv_filename || `Candidate ${index + 1}`,
      target_job: (dashboard.role_family_comparison || {}).jd_family || (dashboard.parsed_jd || {}).role_title || '',
      score: overview.final_score || item.final_score || item.score || 0,
      verdict: overview.verdict || item.verdict || '',
      recommendation: overview.recommendation || '',
      matched_skills: (dashboard.skill_matrix || {}).matched_must_have || [],
      missing_skills: (dashboard.skill_matrix || {}).missing_must_have || [],
      green_flags: dashboard.strengths || [],
      red_flags: dashboard.concerns || []
    };
  });
  const headers = ['Rank','Candidate','Target Job','Score','Verdict','Recommendation','Matched Skills','Missing Skills','Green Flags','Red Flags'];
  const csv = [headers.join(',')].concat(rows.map(row => [
    buildCsvValue(row.rank),
    buildCsvValue(row.candidate),
    buildCsvValue(row.target_job),
    buildCsvValue(`${row.score}%`),
    buildCsvValue(row.verdict),
    buildCsvValue(row.recommendation),
    buildCsvValue(row.matched_skills),
    buildCsvValue(row.missing_skills),
    buildCsvValue(row.green_flags),
    buildCsvValue(row.red_flags)
  ].join(','))).join('\n');
  const blob = new Blob([csv], {type: 'text/csv;charset=utf-8'});
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `jd_cv_match_summaries_${new Date().toISOString().slice(0,10)}.csv`;
  a.click();
  URL.revokeObjectURL(url);
  showToast('Candidate summaries exported', 'success');
}

function currentUserIsAdmin() {
  return Boolean(currentUser && currentUser.is_admin);
}

function verdictClass(verdict, score) {
  const text = String(verdict || '').toLowerCase();
  if (text.includes('strong') || score >= 80) return 'strong';
  if (text.includes('moderate') || score >= 65) return 'moderate';
  if (text.includes('weak') || score >= 45) return 'weak';
  return 'reject';
}

function scoreColor(score) {
  score = Number(score || 0);
  if (score >= 80) return '#52d273';
  if (score >= 65) return '#f1b84b';
  if (score >= 45) return '#e8643a';
  return '#e05252';
}

function renderMatchDashboard(data) {
  const dashboard = data.dashboard || buildDashboardFallback(data);
  const overview = dashboard.overview || {};
  const score = Number(overview.final_score || data.final_score || data.score || 0);
  const verdict = overview.verdict || data.verdict || '';
  const vClass = verdictClass(verdict, score);
  const rawSection = currentUserIsAdmin()
    ? `<details class="match-details-toggle"><summary>Raw JSON</summary>${renderAdminRawJson(data)}</details>`
    : '';
  const recruiterGuide = renderGeminiScreeningReport(data.gemini_screening_report || dashboard.gemini_screening_report || null, {
    error: data.gemini_screening_error || dashboard.gemini_screening_error || '',
    model: data.gemini_screening_model || dashboard.gemini_screening_model || '',
    source: data.gemini_screening_source || dashboard.gemini_screening_source || '',
    usage: data.gemini_screening_usage || dashboard.gemini_screening_usage || {}
  });
  return `
    <div class="match-dashboard minimalist">
      ${renderOverviewCard(overview, vClass)}
      <div class="match-primary-panel">
        ${recruiterGuide}
      </div>
      <details class="match-details-toggle">
        <summary>Recruiter Summary</summary>
        ${renderRecruiterSummary(dashboard.recruiter_summary || data.summary || '')}
      </details>
      <details class="match-details-toggle">
        <summary>Candidate Review</summary>
        ${renderCandidateSummarySection(dashboard.candidate_summary || {}, dashboard)}
        ${renderRoleFamilyComparison(dashboard.role_family_comparison || {})}
        ${renderExperienceComparison(dashboard.experience_comparison || {})}
        ${renderValidationGaps(dashboard.validation_gaps || [], dashboard)}
        ${renderSkillMatrix(dashboard.skill_matrix || {})}
        ${renderTechSkillExperience(dashboard.tech_skills_experience_years || [])}
        ${renderRecentExperience(dashboard.recent_professional_experience || {})}
        ${renderSemanticInsights(dashboard.semantic_insights || [], dashboard.role_alignment_reasoning || [])}
      </details>
      <details class="match-details-toggle">
        <summary>Score Details</summary>
        ${renderWeightedBreakdown(dashboard.score_breakdown || [])}
        ${rawSection}
      </details>
    </div>`;
}

function switchMatchTab(evt, id) {
  const root = evt.target.closest('.match-dashboard');
  root.querySelectorAll('.match-tab').forEach(b => b.classList.remove('active'));
  root.querySelectorAll('.match-panel').forEach(p => p.classList.remove('active'));
  evt.target.classList.add('active');
  root.querySelector('#' + id).classList.add('active');
}

function renderOverviewCard(overview, vClass) {
  const score = Number(overview.final_score || 0);
  const confidence = overview.confidence || {};
  const routing = overview.routing || {};
  const scoringSource = overview.scoring_source || '';
  const manualReview = !!overview.manual_review_required;
  return `
    <div class="match-overview-card ${vClass}">
      <div class="score-ring" style="--score:${score};--scoreColor:${scoreColor(score)}">
        <span>${escapeHtml(score)}</span><small>%</small>
      </div>
      <div class="overview-main">
        <div class="overview-label">Match Overview</div>
        <h2>${escapeHtml(overview.verdict || '-')}</h2>
        <p>${escapeHtml(overview.recommendation || '-')}</p>
        <div class="overview-badges">
          <span class="verdict-badge ${vClass}">${escapeHtml(overview.verdict || '-')}</span>
          <span class="confidence-badge">${escapeHtml(confidence.label || 'Medium')} confidence Â· ${escapeHtml(confidence.score || 0)}%</span>
          ${scoringSource ? `<span class="confidence-badge">${escapeHtml(String(scoringSource).replace(/_/g, ' '))} scoring</span>` : ''}
          ${overview.deterministic_final_score ? `<span class="confidence-badge">Deterministic fallback ${escapeHtml(overview.deterministic_final_score)}%</span>` : ''}
          ${routing.label ? `<span class="confidence-badge">${escapeHtml(routing.label)}</span>` : ''}
          ${manualReview ? `<span class="verdict-badge danger">Manual review required</span>` : ''}
        </div>
      </div>
      ${routing.reason ? `<div class="overview-compact-note">${escapeHtml(routing.reason)}</div>` : ''}
    </div>`;
}

function renderStrengthsConcerns(strengths, concerns) {
  return `
    <div class="match-two-col">
      <div class="match-card success"><h3>Strengths</h3>${renderInsightList(strengths, 'No major strengths extracted.')}</div>
      <div class="match-card warning"><h3>Concerns</h3>${renderInsightList(concerns, 'No major concerns extracted.')}</div>
    </div>`;
}

function renderInsightList(items, emptyText) {
  const arr = Array.isArray(items) ? items.filter(Boolean) : [];
  if (!arr.length) return `<p class="muted">${escapeHtml(emptyText)}</p>`;
  return `<ul class="insight-list">${arr.map(item => `<li>${escapeHtml(item)}</li>`).join('')}</ul>`;
}

function renderWeightedBreakdown(items) {
  const rows = (Array.isArray(items) ? items : []).map(item => {
    const score = Number(item.score || 0);
    const weightPct = Math.round(Number(item.weight || 0) * 100);
    return `
      <div class="breakdown-row">
        <div class="breakdown-head">
          <strong>${escapeHtml(item.label || item.key || '-')}</strong>
          <span>${score}% Â· weight ${weightPct}%</span>
        </div>
        <div class="progress-track"><div class="progress-fill" style="width:${score}%;background:${scoreColor(score)}"></div></div>
        <p>${escapeHtml(item.reason || '')}</p>
      </div>`;
  }).join('');
  return `<div class="match-card"><h3>Weighted Score Breakdown</h3>${rows || '<p class="muted">No score breakdown available.</p>'}</div>`;
}

function renderSkillMatrix(matrix) {
  const matched = matrix.matched_must_have || [];
  const missing = matrix.missing_must_have || [];
  const candidate = matrix.candidate_skills || [];
  return `
    <div class="match-grid-3">
      <div class="match-card success"><h3>Matched Must-Haves</h3>${renderSkillBadges(matched, 'matched')}</div>
      <div class="match-card danger"><h3>Missing Must-Haves</h3>${renderSkillBadges(missing, 'missing')}</div>
      <div class="match-card"><h3>Candidate Skill Evidence</h3>${renderSkillBadges(candidate, 'neutral')}</div>
    </div>`;
}

function renderSkillBadges(items, type) {
  const arr = Array.isArray(items) ? items.filter(Boolean) : [];
  if (!arr.length) return '<p class="muted">None found.</p>';
  return `<div class="skill-badge-wrap">${arr.map(x => `<span class="skill-badge ${type}">${escapeHtml(x)}</span>`).join('')}</div>`;
}

function renderCandidateSnapshot(snapshot) {
  return `
    <div class="match-card">
      <h3>Candidate Snapshot</h3>
      <div class="snapshot-grid">
        <div><label>Current Role</label><strong>${escapeHtml(snapshot.current_role || '-')}</strong></div>
        <div><label>Experience</label><strong>${escapeHtml(snapshot.experience_years || 0)} years</strong></div>
        <div><label>Location</label><strong>${escapeHtml(snapshot.location || '-')}</strong></div>
        <div><label>Employment Status</label><strong>${escapeHtml(snapshot.employment_status || '-')}</strong></div>
        <div><label>Last Employed</label><strong>${escapeHtml(snapshot.last_employed_date || '-')}</strong></div>
        <div><label>AI Optimization Risk</label><strong>${escapeHtml((snapshot.ai_optimization_risk || {}).label || '-')}</strong></div>
        <div><label>Education</label><strong>${escapeHtml((snapshot.education || []).join(', ') || '-')}</strong></div>
        <div><label>Domains</label><strong>${escapeHtml((snapshot.domains || []).join(', ') || '-')}</strong></div>
      </div>
      ${renderCareerGaps(snapshot.career_gap_periods || [])}
      <div style="margin-top:14px"><label class="mini-label">Top Skills</label>${renderSkillBadges(snapshot.top_skills || [], 'neutral')}</div>
    </div>`;
}

function renderCareerGaps(gaps) {
  const arr = Array.isArray(gaps) ? gaps.filter(Boolean) : [];
  if (!arr.length) return '';
  return `<div style="margin-top:14px"><label class="mini-label">Career Gaps</label>${renderInsightList(arr.map(g => `${g.start || '-'} to ${g.end || '-'} (${g.duration_months || 0} months)`), 'No career gaps detected.')}</div>`;
}

function renderRoleHistory(roles) {
  const arr = Array.isArray(roles) ? roles.filter(r => r && (r.title || r.company || (r.responsibilities || []).length)) : [];
  if (!arr.length) {
    return `<div class="match-card"><h3>Latest Job Roles and Responsibilities</h3><p class="muted">No role history could be extracted from the resume.</p></div>`;
  }
  return `
    <div class="match-card">
      <h3>Latest Job Roles and Responsibilities</h3>
      <div class="role-history-list">
        ${arr.map(role => `
          <div class="role-history-item">
            <div class="role-history-head">
              <div>
                <strong>${escapeHtml(role.title || 'Role not specified')}</strong>
                <span>${escapeHtml(role.company || 'Company not specified')}</span>
              </div>
              <em>${escapeHtml(role.duration_years || 0)} yrs</em>
            </div>
            ${renderInsightList(role.responsibilities || [], 'No responsibilities extracted for this role.')}
            ${renderSkillBadges(role.skills_used || [], 'neutral')}
          </div>
        `).join('')}
      </div>
    </div>`;
}

function renderRecruiterSummary(summary) {
  return `
    <div class="match-card">
      <div style="display:flex;justify-content:space-between;gap:12px;align-items:center">
        <h3>Hiring Manager Summary</h3>
        <div style="display:flex;gap:8px;flex-wrap:wrap">
          <button class="btn btn-outline" type="button" onclick="copyRecruiterSummary(this)">Copy Summary</button>
          <button class="btn" type="button" onclick="exportCurrentMatchPdf()">Export PDF</button>
        </div>
      </div>
      <textarea class="hm-summary-box" readonly>${escapeHtml(summary || '-')}</textarea>
    </div>`;
}

function renderCandidateSummarySection(summary, dashboard) {
  const score = Number(summary.score_percent || dashboard?.overview?.final_score || 0);
  const confidence = (summary.confidence || dashboard?.overview?.confidence || {});
  return `
    <div class="match-card success">
      <h3>Candidate Summary</h3>
      <div class="snapshot-grid">
        <div><label>Match Score</label><strong>${escapeHtml(score)}%</strong></div>
        <div><label>Verdict</label><strong>${escapeHtml(summary.verdict || dashboard?.overview?.verdict || '-')}</strong></div>
        <div><label>Recommendation</label><strong>${escapeHtml(summary.recommendation || dashboard?.overview?.recommendation || '-')}</strong></div>
        <div><label>Confidence</label><strong>${escapeHtml(confidence.label || '-')} (${escapeHtml(confidence.score || 0)}%)</strong></div>
      </div>
    </div>`;
}

function renderRoleFamilyComparison(comparison) {
  const jdSkills = Array.isArray(comparison.jd_skills) ? comparison.jd_skills : [];
  const candidateSkills = Array.isArray(comparison.candidate_skills) ? comparison.candidate_skills : [];
  const shared = Array.isArray(comparison.shared_skills) ? comparison.shared_skills : [];
  const validation = Array.isArray(comparison.validation_evidence) ? comparison.validation_evidence : [];
  return `
    <div class="match-card">
      <h3>Role Family Comparison</h3>
      <div class="snapshot-grid">
        <div><label>JD Role Family</label><strong>${escapeHtml(comparison.jd_family || '-')}</strong></div>
        <div><label>CV Role Family</label><strong>${escapeHtml(comparison.candidate_family || '-')}</strong></div>
      </div>
      <p style="margin-top:10px">${escapeHtml(comparison.match_summary || 'Role family comparison not available.')}</p>
      <div style="margin-top:12px"><label class="mini-label">JD Skills</label>${renderSkillBadges(jdSkills, 'neutral')}</div>
      <div style="margin-top:12px"><label class="mini-label">CV Skills</label>${renderSkillBadges(candidateSkills, 'neutral')}</div>
      <div style="margin-top:12px"><label class="mini-label">Shared Skills</label>${renderSkillBadges(shared, 'matched')}</div>
      ${validation.length ? `<div style="margin-top:12px"><label class="mini-label">JD Validation Evidence</label>${renderSkillBadges(validation, 'neutral')}</div>` : ''}
    </div>`;
}

function renderExperienceComparison(exp) {
  return `
    <div class="match-card warning">
      <h3>Experience Comparison</h3>
      <div class="snapshot-grid">
        <div><label>JD Requirement</label><strong>${escapeHtml(exp.jd_required || '-')}</strong></div>
        <div><label>Candidate Experience</label><strong>${escapeHtml(exp.candidate_years || 0)} years</strong></div>
        <div><label>Fit Summary</label><strong>${escapeHtml(exp.fit_summary || '-')}</strong></div>
        <div><label>Within Range</label><strong>${escapeHtml(exp.is_within_range ? 'Yes' : 'No')}</strong></div>
      </div>
    </div>`;
}

function renderTechSkillExperience(rows) {
  const arr = Array.isArray(rows) ? rows.filter(r => r && r.skill) : [];
  if (!arr.length) return `<div class="match-card"><h3>Technical Skills Experience</h3><p class="muted">No skill duration evidence could be inferred.</p></div>`;
  return `
    <div class="match-card">
      <h3>Technical Skills Experience in Years</h3>
      <div class="role-history-list">
        ${arr.map(row => `
          <div class="role-history-item">
            <div class="role-history-head">
              <div>
                <strong>${escapeHtml(row.skill)}</strong>
                <span>${escapeHtml((row.evidence_roles || []).join(', ') || 'Evidence from role history')}</span>
              </div>
              <em>${escapeHtml(row.years || 0)} yrs</em>
            </div>
          </div>
        `).join('')}
      </div>
    </div>`;
}

function renderRecentExperience(recent) {
  const ach = Array.isArray(recent.achievements) ? recent.achievements : [];
  const resp = Array.isArray(recent.responsibilities) ? recent.responsibilities : [];
  const skills = Array.isArray(recent.skills_used) ? recent.skills_used : [];
  if (!recent || (!recent.title && !recent.company && !ach.length && !resp.length)) {
    return `<div class="match-card"><h3>Most Recent Professional Experience</h3><p class="muted">No recent role details could be extracted.</p></div>`;
  }
  return `
    <div class="match-card">
      <h3>Most Recent Professional Experience</h3>
      <div class="snapshot-grid">
        <div><label>Title</label><strong>${escapeHtml(recent.title || '-')}</strong></div>
        <div><label>Company</label><strong>${escapeHtml(recent.company || '-')}</strong></div>
        <div><label>Duration</label><strong>${escapeHtml(recent.duration_years || 0)} years</strong></div>
      </div>
      <div style="margin-top:12px"><label class="mini-label">Achievements / Tangible Output</label>${renderInsightList(ach, 'No tangible achievement bullets could be isolated.')}</div>
      <div style="margin-top:12px"><label class="mini-label">Responsibilities</label>${renderInsightList(resp, 'No responsibilities extracted.')}</div>
      <div style="margin-top:12px"><label class="mini-label">Skills Used</label>${renderSkillBadges(skills, 'neutral')}</div>
    </div>`;
}

function renderValidationGaps(gaps, dashboard) {
  const arr = Array.isArray(gaps) ? gaps.filter(Boolean) : [];
  const jdWarn = (dashboard?.parsed_jd?.parser_warnings || dashboard?.candidate_snapshot?.parser_warnings || []);
  const cvWarn = (dashboard?.parsed_candidate?.parser_warnings || []);
  const warnings = [...new Set([...(Array.isArray(jdWarn) ? jdWarn : []), ...(Array.isArray(cvWarn) ? cvWarn : [])])].filter(Boolean);
  const manualReview = dashboard?.manual_review || {};
  if (!arr.length && !warnings.length && !manualReview.required) {
    return `<div class="match-card"><h3>Validation Gaps</h3><p class="muted">No explicit validation gaps were generated for this match.</p></div>`;
  }
  return `
    <div class="match-card warning">
      <h3>Validation Gaps</h3>
      ${manualReview.required ? `
        <div class="breakdown-row" style="margin-bottom:12px">
          <div class="breakdown-head">
            <strong>Manual Review Required</strong>
            <span>DRAFT</span>
          </div>
          <p>${escapeHtml(manualReview.summary || 'Manual recruiter review required before action.')}</p>
          ${renderInsightList(Array.isArray(manualReview.reasons) ? manualReview.reasons : [], 'No manual review reasons listed.')}
        </div>
      ` : ''}
      ${arr.map(g => `
        <div class="breakdown-row" style="margin-bottom:12px">
          <div class="breakdown-head">
            <strong>${escapeHtml(g.area || 'Validation')}</strong>
            <span>${escapeHtml((g.severity || 'medium').toUpperCase())}</span>
          </div>
          <p>${escapeHtml(g.message || '')}</p>
          ${renderInsightList(Array.isArray(g.evidence) ? g.evidence : [], 'No evidence listed.')}
        </div>
      `).join('')}
      ${warnings.length ? `<div style="margin-top:10px"><label class="mini-label">Parser Warnings</label>${renderInsightList(warnings, 'No parser warnings.')}</div>` : ''}
    </div>`;
}

function renderGeminiScreeningReport(report, meta) {
  meta = meta || {};
  const errorMessage = meta.error || '';
  const usage = meta.usage || {};
  const usageBits = [
    usage.prompt_token_count != null ? `prompt ${usage.prompt_token_count}` : '',
    usage.candidates_token_count != null ? `completion ${usage.candidates_token_count}` : '',
    usage.total_token_count != null ? `total ${usage.total_token_count}` : ''
  ].filter(Boolean);
  if (!report) {
    return `
      <div class="match-card">
        <h3>Recruiter Guide</h3>
        <p class="muted">${escapeHtml(errorMessage || 'Gemini screening report is not available yet. Configure GEMINI_API_KEY and run a fresh match to generate it.')}</p>
      </div>`;
  }
  const rows = Array.isArray(report.requirement_matches) ? report.requirement_matches : [];
  const greenFlags = Array.isArray(report.green_flags) ? report.green_flags : [];
  const redFlags = Array.isArray(report.red_flags) ? report.red_flags : [];
  const questions = Array.isArray(report.screening_questions) ? report.screening_questions : [];
  return `
    <div class="match-card success">
        <h3>Recruiter Guide</h3>
      ${meta.model || meta.source ? `<p class="muted" style="margin-top:-4px;margin-bottom:12px">${escapeHtml([meta.source, meta.model].filter(Boolean).join(' · '))}</p>` : ''}
      ${usageBits.length ? `<p class="muted" style="margin-top:-6px;margin-bottom:12px">Tokens used: ${escapeHtml(usageBits.join(' · '))}</p>` : ''}
      <div class="snapshot-grid">
        <div><label>Candidate Name</label><strong>${escapeHtml(report.candidate_name || '-')}</strong></div>
        <div><label>Target Job</label><strong>${escapeHtml(report.target_job_title || '-')}</strong></div>
        <div><label>Score</label><strong>${escapeHtml(report.final_score ?? '-')}%</strong></div>
        <div><label>ATS Verdict</label><strong>${escapeHtml(report.ats_verdict || '-')}</strong></div>
        <div><label>Call / Reject</label><strong>${escapeHtml(report.call_or_reject || '-')}</strong></div>
        <div><label>Recommendation</label><strong>${escapeHtml(report.recommendation || '-')}</strong></div>
      </div>
      <div style="margin-top:14px">
        <label class="mini-label">Requirement Matches</label>
        <div style="overflow:auto">
          <table class="req-table" style="min-width:100%;background:#151924">
            <thead>
              <tr>
                <th>What the Job Asks For</th>
                <th>What the Candidate Actually Has</th>
                <th>Recruiter Verdict</th>
              </tr>
            </thead>
            <tbody>
              ${rows.map(row => `
                <tr>
                  <td>${escapeHtml(row.what_the_job_asks_for || '-')}</td>
                  <td>${escapeHtml(row.what_the_candidate_actually_has || '-')}</td>
                  <td>${escapeHtml(row.junior_recruiter_verdict || '-')}</td>
                </tr>`).join('')}
            </tbody>
          </table>
        </div>
      </div>
      <div class="match-two-col" style="margin-top:14px">
        <div class="match-card success" style="margin:0">
          <h3>Why to Shortlist Them (Green Flags)</h3>
          ${renderInsightList(greenFlags, 'No green flags returned.')}
        </div>
        <div class="match-card warning" style="margin:0">
          <h3>Why to Be Careful (Red Flags & Gaps)</h3>
          ${renderInsightList(redFlags, 'No red flags returned.')}
        </div>
      </div>
      <div style="margin-top:14px">
        <h3 style="margin:0 0 10px 0;font-size:15px">The Recruiter Interview Cheat Sheet</h3>
        <div class="role-history-list">
          ${questions.map((item, index) => `
            <div class="role-history-item">
              <div class="role-history-head">
                <div>
                  <strong>Question ${index + 1}</strong>
                  <span>${escapeHtml(item.question || '-')}</span>
                </div>
              </div>
              <p><strong>Bad answer:</strong> ${escapeHtml(item.bad_answer || '-')}</p>
              <p><strong>Good answer:</strong> ${escapeHtml(item.good_answer || '-')}</p>
            </div>
          `).join('')}
        </div>
      </div>
    </div>`;
}

async function exportCurrentMatchPdf() {
  if (!window.currentMatchAnalysis) {
    showToast('Run match analysis first', 'error');
    return;
  }
  try {
    const res = await fetch('/api/match/export_pdf', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(window.currentMatchAnalysis)
    });
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      throw new Error(data.error || 'Unable to export PDF');
    }
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    const dashboard = window.currentMatchAnalysis.dashboard || buildDashboardFallback(window.currentMatchAnalysis);
    const candidateName = ((dashboard.candidate_snapshot || {}).candidate_name || window.currentMatchAnalysis.cv_filename || 'candidate')
      .replace(/[^A-Za-z0-9_-]+/g, '_')
      .replace(/^_+|_+$/g, '') || 'candidate';
    a.href = url;
    a.download = `match_analysis_${candidateName}_${new Date().toISOString().slice(0,10)}.pdf`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
    showToast('PDF exported', 'success');
  } catch(e) {
    showToast(e.message, 'error');
  }
}

function copyRecruiterSummary(btn) {
  const text = btn.closest('.match-card').querySelector('.hm-summary-box').value;
  navigator.clipboard.writeText(text).then(() => showToast('Summary copied', 'success')).catch(() => showToast('Unable to copy summary', 'error'));
}

function renderPenaltyDashboard(penalties) {
  const arr = Array.isArray(penalties) ? penalties.filter(p => p && p.reason) : [];
  if (!arr.length) return `<div class="match-card"><h3>Penalties</h3><p class="muted">No explicit penalties applied.</p></div>`;
  return `
    <div class="match-card danger">
      <h3>Penalties Applied</h3>
      ${arr.map(p => {
        const impact = Math.abs(Number(p.impact || 0));
        return `<div class="penalty-row"><span>${escapeHtml(p.reason)}</span><strong>-${impact}</strong><div class="penalty-bar"><i style="width:${Math.min(100, impact * 5)}%"></i></div></div>`;
      }).join('')}
    </div>`;
}

function renderSemanticInsights(insights, roleReasoning) {
  return `
    <div class="match-two-col">
      <div class="match-card"><h3>Semantic Insights</h3>${renderInsightList(insights, 'No semantic insights available.')}</div>
      <div class="match-card"><h3>Role Alignment Reasoning</h3>${renderInsightList(roleReasoning, 'No role reasoning available.')}</div>
    </div>`;
}

function renderAdminRawJson(data) {
  return `<div class="match-card"><h3>Raw JSON</h3><pre class="raw-json">${escapeHtml(JSON.stringify(data, null, 2))}</pre></div>`;
}

function buildDashboardFallback(data) {
  const scoreJson = data.score_json || {};
  return {
    overview: {
      final_score: scoreJson.final_score ?? data.final_score ?? data.score ?? 0,
      structured_score: data.structured_score ?? 0,
      semantic_score: data.semantic_score ?? 0,
      verdict: scoreJson.verdict || data.verdict || '',
      recommendation: '',
      confidence: {label:'Medium', score:70},
      manual_review_required: (data.manual_review || {}).required || false
    },
    score_breakdown: Object.entries(scoreJson.score_breakdown || data.score_breakdown || {}).map(([key, value]) => ({key, label:key.replace(/_/g,' '), score: typeof value === 'object' ? value.score : value, weight:0, reason: typeof value === 'object' ? value.reason : ''})),
    strengths: scoreJson.strengths || data.strengths || [],
    concerns: scoreJson.concerns || data.concerns || data.gaps || [],
    skill_matrix: {matched_must_have: scoreJson.matched_must_have_skills || data.matched_must_have_skills || [], missing_must_have: scoreJson.missing_must_have_skills || data.missing_must_have_skills || [], candidate_skills: (data.cv_json || {}).normalized_skills || (data.cv_json || {}).primary_skills || []},
    candidate_snapshot: {current_role:(data.cv_json || {}).current_role || '', experience_years:(data.cv_json || {}).total_experience_years || 0, education:(data.cv_json || {}).education || [], domains:(data.cv_json || {}).domain_experience || [], top_skills:(data.cv_json || {}).normalized_skills || (data.cv_json || {}).primary_skills || []},
    role_history: (data.cv_json || {}).role_history || [],
    candidate_summary: {score_percent: scoreJson.final_score ?? data.final_score ?? data.score ?? 0, verdict: scoreJson.verdict || data.verdict || '', recommendation: data.recommendation || '', confidence: {label:'Medium', score:70}},
    role_family_comparison: {
      jd_family:(data.jd_json || {}).taxonomy?.primary_role_family || (data.jd_json || {}).role_profile?.name || (data.jd_json || {}).primary_role || (data.jd_json || {}).role_title || '-',
      candidate_family:(data.cv_json || {}).taxonomy?.primary_role_family || (data.cv_json || {}).normalized_roles?.[0] || (data.cv_json || {}).current_role || '-',
      jd_skills:(data.jd_json || {}).must_have_skills || [],
      candidate_skills:(data.cv_json || {}).normalized_skills || (data.cv_json || {}).primary_skills || [],
      shared_skills: [],
      validation_evidence:(data.jd_json || {}).validation_evidence || [],
      match_summary: ''
    },
    experience_comparison: {jd_required: ((data.jd_json || {}).experience_required?.min_years || 0) + ((data.jd_json || {}).experience_required?.max_years ? '-' + (data.jd_json || {}).experience_required.max_years : '+') + ' years', candidate_years:(data.cv_json || {}).total_experience_years || 0, fit_summary:'', is_within_range:true},
    tech_skills_experience_years: [],
    recent_professional_experience: ((data.cv_json || {}).role_history || [])[0] || {},
    parsed_jd: data.jd_json || {},
    parsed_candidate: data.cv_json || {},
    validation_gaps: data.validation_gaps || [],
    manual_review: data.manual_review || {},
    penalties: scoreJson.penalties_applied || data.penalties_applied || [],
    semantic_insights: data.semantic_match_insights || [],
    role_alignment_reasoning: data.role_alignment_reasoning || [],
    recruiter_summary: data.overall_recruiter_summary || data.summary || ''
  };
}

function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>"']/g, function(ch) {
    return ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'})[ch];
  });
}

function escapeJs(value) {
  return String(value ?? '').replace(/[\\'"]/g, function(ch) {
    return ({'\\':'\\\\', "'":"\\'", '"':'&quot;'})[ch];
  }).replace(/\n/g, ' ');
}

function renderSimpleList(items, emptyText) {
  const arr = Array.isArray(items) ? items.filter(Boolean) : [];
  if (!arr.length) return '<li>' + escapeHtml(emptyText) + '</li>';
  return arr.map(x => '<li>' + escapeHtml(x) + '</li>').join('');
}

function renderPenalties(items) {
  const arr = Array.isArray(items) ? items.filter(p => p && p.reason) : [];
  if (!arr.length) return '';
  return `
    <div class="stat-card" style="margin-top:16px">
      <div class="card-title">Penalties Applied</div>
      <ul style="margin-left:18px">
        ${arr.map(p => '<li>' + escapeHtml(p.reason) + ' <strong style="color:#e8643a">-' + escapeHtml(p.impact || 0) + '</strong></li>').join('')}
      </ul>
    </div>`;
}

function renderScoreBreakdown(breakdown) {
  const labels = {
    must_have_skills: 'Must-Have Skills',
    role_alignment: 'Role Alignment',
    role_relevance: 'Role Relevance',
    experience_fit: 'Experience Fit',
    domain_fit: 'Domain Fit',
    seniority_fit: 'Seniority Fit',
    nice_to_have: 'Nice-to-Have',
    secondary_skills: 'Secondary Skills',
    stability: 'Stability',
    contextual_intelligence: 'Context'
  };
  const entries = Object.keys(labels)
    .filter(key => Object.prototype.hasOwnProperty.call(breakdown, key))
    .map(key => [labels[key], breakdown[key] ?? 0]);
  return `
    <div class="stat-card" style="margin-bottom:16px">
      <div class="card-title">Score Breakdown</div>
      <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px">
        ${entries.map(([label, value]) => `
          <div style="background:#202636;border:1px solid #2a3246;border-radius:6px;padding:10px">
            <div style="font-size:12px;color:#8b95b5">${escapeHtml(label)}</div>
            <div style="font-size:20px;font-weight:800;color:#f5f7fb">${escapeHtml(value)}%</div>
          </div>`).join('')}
      </div>
    </div>`;
}

function renderStructuredHiringData(jd, cv, score) {
  const must = renderSimpleList(jd.must_have_skills || [], 'No must-have skills extracted.');
  const missing = renderSimpleList(score.missing_must_have_skills || [], 'No missing must-have skills.');
  const matched = renderSimpleList(score.matched_must_have_skills || [], 'No matched must-have skills.');
  const primary = Array.isArray(cv.primary_skills) ? cv.primary_skills.join(', ') : '';
  return `
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-top:16px">
      <div class="stat-card">
        <div class="card-title">Parsed JD</div>
        <div class="detail-field"><label>Role</label><span>${escapeHtml(jd.role_title || '-')}</span></div>
        <div class="detail-field"><label>Category</label><span>${escapeHtml(jd.role_category || '-')}</span></div>
        <div class="detail-field"><label>Experience</label><span>${escapeHtml((jd.experience_required?.min_years || 0) + (jd.experience_required?.max_years ? '-' + jd.experience_required.max_years : '+') + ' years')}</span></div>
        <div class="detail-field"><label>Domain</label><span>${escapeHtml(jd.domain || '-')}</span></div>
        <div style="margin-top:10px"><label style="color:#8b95b5;font-size:12px">Must-Have Skills</label><ul style="margin-left:18px">${must}</ul></div>
      </div>
      <div class="stat-card">
        <div class="card-title">Parsed Candidate</div>
        <div class="detail-field"><label>Name</label><span>${escapeHtml(cv.candidate_name || '-')}</span></div>
        <div class="detail-field"><label>Current Role</label><span>${escapeHtml(cv.current_role || '-')}</span></div>
        <div class="detail-field"><label>Experience</label><span>${escapeHtml(cv.total_experience_years || 0)} years</span></div>
        <div class="detail-field"><label>Primary Skills</label><span>${escapeHtml(primary || '-')}</span></div>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-top:10px">
          <div><label style="color:#8b95b5;font-size:12px">Matched Must-Haves</label><ul style="margin-left:18px">${matched}</ul></div>
          <div><label style="color:#8b95b5;font-size:12px">Missing Must-Haves</label><ul style="margin-left:18px">${missing}</ul></div>
        </div>
      </div>
    </div>`;
}

function renderCandidateSummary(summary) {
  const hasData = Object.values(summary || {}).some(v => Array.isArray(v) ? v.length : v);
  if (!hasData) return '';
  const skills = Array.isArray(summary.key_skills) ? summary.key_skills.join(', ') : (summary.key_skills || '-');
  return `
    <div class="stat-card" style="margin-top:16px">
      <div class="card-title">Candidate Summary From CV</div>
      <div style="display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px">
        <div class="detail-field"><label>Current Designation</label><span>${summary.current_designation || '-'}</span></div>
        <div class="detail-field"><label>Total Experience</label><span>${summary.total_experience || '-'}</span></div>
        <div class="detail-field"><label>Education</label><span>${summary.education || '-'}</span></div>
        <div class="detail-field"><label>Current Company</label><span>${summary.current_company || '-'}</span></div>
        <div class="detail-field" style="grid-column:1/-1"><label>Key Skills</label><span>${skills || '-'}</span></div>
        <div class="detail-field" style="grid-column:1/-1"><label>Relevant Details</label><span>${summary.relevant_details || '-'}</span></div>
      </div>
    </div>`;
}

function clearJdMatch() {
  document.getElementById('jdMatchJd').value = '';
  document.getElementById('jdMatchText').value = '';
  const interviewJd = document.getElementById('interviewJdFile');
  if (interviewJd) interviewJd.value = '';
  const interviewText = document.getElementById('interviewJdText');
  if (interviewText) interviewText.value = '';
  document.getElementById('jdMatchAlert').style.display = 'none';
  const result = document.getElementById('jdCriteriaResult');
  if (result) result.innerHTML = 'Upload or paste a JD, then analyse it to review role responsibilities, experience, tech skills, location, education, and certifications.';
  window.currentMatchAnalysis = null;
  window.currentBatchMatches = [];
  window.currentExtractedJd = null;
  const panel = document.getElementById('screeningQuestionsPanel');
  if (panel) panel.innerHTML = 'Questions will open in a separate window after generation.';
  updateInterviewJdFileName();
  updateJdMatchStatus();
}



let topNavMenuCloseTimer = null;
function closeTopNavMenus() {
  document.body.classList.add('topnav-menu-collapsed');
  clearTimeout(topNavMenuCloseTimer);
  topNavMenuCloseTimer = setTimeout(() => {
    if (!document.querySelector('.topnav-links:hover')) {
      document.body.classList.remove('topnav-menu-collapsed');
    }
  }, 900);
}

function switchTab(tabName) {
  closeTopNavMenus();
  document.querySelectorAll('.tab-link').forEach(l => l.classList.remove('active'));
  document.querySelectorAll('.topnav-link').forEach(l => l.classList.remove('active'));
  document.querySelectorAll('.topnav-subitem').forEach(l => l.classList.remove('active'));
  document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
  const navLink = document.querySelector('[data-tab="' + tabName + '"]');
  if (navLink) navLink.classList.add('active');
  const topKey = ['jd-match', 'jd-cv-match', 'resume-analysis'].includes(tabName) ? 'screening'
    : ['reporting', 'reports'].includes(tabName) ? 'reporting'
    : ['admin-setup', 'user-management'].includes(tabName) ? 'setup'
    : ['candidate-search', 'requirements', 'power-search', 'ats-workspace'].includes(tabName) ? 'sourcing'
    : tabName;
  const topLink = document.querySelector('[data-top-tab="' + topKey + '"]');
  if (topLink) topLink.classList.add('active');
  const aiLink = document.querySelector('[data-ai-tab="' + tabName + '"]');
  if (aiLink) aiLink.classList.add('active');
  const tabEl = document.getElementById('tab-' + tabName);
  if (!tabEl) return;
  tabEl.classList.add('active');
  ensureTabDataLoaded(tabName);
  
}

function markTabDataLoaded(tabName) {
  if (tabName) loadedTabData.add(tabName);
}

function ensureTabDataLoaded(tabName, {force=false} = {}) {
  if (!tabName) return Promise.resolve();
  if (!force && loadedTabData.has(tabName)) return Promise.resolve();
  markTabDataLoaded(tabName);
  if (tabName === 'ats-workspace') {
    if (suppressWorkspaceAutoLoad) return Promise.resolve();
    return loadRecruiterDashboardSummary({light:true, deferFull:true});
  }
  if (tabName === 'candidate-search') return runCandidateSearch();
  if (tabName === 'power-search') return runPowerSearch();
  if (tabName === 'reports') return loadReportData();
  if (tabName === 'reporting') {
    hideReportingDateFilters();
    return loadFilterOptions().then(() => loadReportingCandidates());
  }
  if (tabName === 'pipelines') return loadPipelines();
  if (tabName === 'jobs') return loadJobs();
  if (tabName === 'team') return loadTeam();
  if (tabName === 'user-management') return loadUsers();
  if (tabName === 'requirements') return loadRequirements();
  if (tabName === 'resume-analysis') return loadResumeDefaultPrompt();
  if (tabName === 'profile') return loadProfilePage();
  if (tabName === 'admin-setup') return loadFilterOptions();
  return Promise.resolve();
}

function setTopNavActive(key) {
  document.querySelectorAll('.topnav-link').forEach(l => l.classList.remove('active'));
  document.querySelectorAll('.topnav-subitem').forEach(l => l.classList.remove('active'));
  const topLink = document.querySelector('[data-top-tab="' + key + '"]');
  if (topLink) topLink.classList.add('active');
}

function openAtsWorkspacePage(pageId, topKey='sourcing') {
  closeTopNavMenus();
  suppressWorkspaceAutoLoad = true;
  switchTab('ats-workspace');
  suppressWorkspaceAutoLoad = false;
  showAtsPage(pageId);
  setTopNavActive(topKey);
  if (pageId === 'atsDashboard') {
    markTabDataLoaded('ats-workspace');
    loadCandidateStats();
    loadDashboardCandidateList();
  }
}

function showAtsPage(pageId, btn) {
  document.querySelectorAll('#tab-ats-workspace .ats-page').forEach(page => page.style.display = 'none');
  const page = document.getElementById(pageId);
  if (page) page.style.display = '';
  if (pageId === 'atsAddApplicant') loadRecruiterDashboardSummary({light: !dashboardSummaryFullLoaded, deferFull: true});
  if (btn) {
    document.querySelectorAll('#tab-ats-workspace .ats-tab').forEach(tab => tab.classList.remove('active'));
    btn.classList.add('active');
  }
}

function openCommunicationCentre(panelId='candidateOutreachTemplates') {
  closeTopNavMenus();
  suppressWorkspaceAutoLoad = true;
  switchTab('ats-workspace');
  suppressWorkspaceAutoLoad = false;
  showAtsPage('atsCommunicationCentre');
  setTopNavActive('sourcing');
  const link = document.querySelector('[data-communication-link="' + panelId + '"]');
  showCommunicationPanel(panelId, link);
  loadLinkedInTemplate(1, document.querySelector('.campaign-template-tab.active'));
}

function handleInitialAppHash() {
  const key = String(window.location.hash || '').replace(/^#/, '').trim();
  if (!key) return;
  const actions = {
    landing: () => openAtsWorkspacePage('atsAddApplicant', 'sourcing'),
    pipeline: () => openAtsWorkspacePage('atsDashboard', 'sourcing'),
    requirements: () => switchTab('requirements'),
    'candidate-search': () => switchTab('candidate-search'),
    search: () => switchTab('candidate-search'),
    reporting: () => switchTab('reporting'),
    'add-candidate': () => openAtsApplicantForm('manual'),
    'add-requirement': () => showAddRequirementModal(),
    profile: () => switchTab('profile')
  };
  const run = actions[key];
  if (run) setTimeout(run, 50);
}

window.addEventListener('hashchange', handleInitialAppHash);

function showCommunicationPanel(panelId, btn) {
  document.querySelectorAll('.campaign-panel').forEach(panel => panel.classList.remove('active'));
  document.querySelectorAll('.communication-link').forEach(link => link.classList.remove('active'));
  const panel = document.getElementById(panelId);
  if (panel) panel.classList.add('active');
  if (btn) btn.classList.add('active');
}

function getLinkedInCampaignTemplate(step) {
  const segment = document.getElementById('linkedinCampaignSegment')?.value || 'Initial Outreach';
  const skillLine = document.getElementById('linkedinCampaignSkillFilter')?.value?.trim()
    ? `This role is aligned to ${document.getElementById('linkedinCampaignSkillFilter').value.trim()}.`
    : 'We have a role that may match your background and current interests.';
  if (step === 2 || segment === 'Follow-up Email') {
    return {
      subject: 'Following up on the opportunity we shared',
      body: `Hi {% raw %}{{first_name}}{% endraw %},

Just checking in to see whether you had a chance to review the role we shared earlier.

${skillLine}

If you would like, I can share a few more details or discuss similar opportunities.

Regards,
{% raw %}{{recruiter_name}}{% endraw %}
{% raw %}{{company_name}}{% endraw %}`
    };
  }
  if (step === 3 || segment === 'Final Reminder') {
    return {
      subject: 'A quick final reminder on the opportunity',
      body: `Hi {% raw %}{{first_name}}{% endraw %},

I wanted to send one last reminder about the opportunity we shared.

${skillLine}

If this is not the right fit, no problem. I can still keep you in mind for future roles.

Regards,
{% raw %}{{recruiter_name}}{% endraw %}
{% raw %}{{company_name}}{% endraw %}`
    };
  }
  if (step === 4 || segment === 'Referral Nudge') {
    return {
      subject: 'Know someone who may be a fit for this role?',
      body: `Hi {% raw %}{{first_name}}{% endraw %},

If this role is not a fit for you, you can still help by sharing it with someone in your network who may be interested.

${skillLine}

Please feel free to forward this message to a friend or colleague.

Regards,
{% raw %}{{recruiter_name}}{% endraw %}
{% raw %}{{company_name}}{% endraw %}`
    };
  }
  return {
    subject: 'Initial outreach for a role that may fit your profile',
    body: `Hi {% raw %}{{first_name}}{% endraw %},

We came across your profile and wanted to share a relevant opportunity with you.

${skillLine}

If this looks suitable, please reply and we can take it forward.

Regards,
{% raw %}{{recruiter_name}}{% endraw %}
{% raw %}{{company_name}}{% endraw %}`
  };
}

function loadLinkedInTemplate(step, btn) {
  document.querySelectorAll('.campaign-template-tab').forEach(tab => tab.classList.remove('active'));
  if (btn) btn.classList.add('active');
  const template = getLinkedInCampaignTemplate(step);
  setValue('linkedinCampaignSubject', template.subject);
  setValue('linkedinCampaignBody', template.body);
}

function updateLinkedInCampaignCopy() {
  const activeTab = document.querySelector('.campaign-template-tab.active');
  const index = Array.from(document.querySelectorAll('.campaign-template-tab')).indexOf(activeTab);
  loadLinkedInTemplate(index >= 0 ? index + 1 : 1, activeTab);
}

function generateLinkedInTrackingLink() {
  const url = valueOf('linkedinCampaignUrl').trim();
  if (!url) {
    showToast('Add the LinkedIn company page URL first.', 'error');
    return;
  }
  const separator = url.includes('?') ? '&' : '?';
  const segment = encodeURIComponent(valueOf('linkedinCampaignSegment').trim().toLowerCase().replace(/\s+/g, '-'));
  setValue('linkedinCampaignTracking', `${url}${separator}utm_source=ats_email&utm_medium=email&utm_campaign=linkedin_follow_${segment}`);
  showToast('Tracking link generated.', 'success');
}

function getLinkedInCampaignPayload() {
  return {
    linkedin_page_url: valueOf('linkedinCampaignUrl').trim(),
    target_segment: valueOf('linkedinCampaignSegment').trim(),
    email_subject: valueOf('linkedinCampaignSubject').trim(),
    email_body: valueOf('linkedinCampaignBody').trim(),
    send_schedule: valueOf('linkedinCampaignSchedule').trim(),
    tracking_link: valueOf('linkedinCampaignTracking').trim(),
    follow_up_step: valueOf('linkedinCampaignFollowup').trim(),
    audience_filters: {
      keyword: valueOf('linkedinCampaignKeywordFilter').trim(),
      status: valueOf('linkedinCampaignStatusFilter').trim(),
      client: valueOf('linkedinCampaignClientFilter').trim(),
      skill: valueOf('linkedinCampaignSkillFilter').trim(),
      max_recipients: valueOf('linkedinCampaignMaxRecipients').trim()
    },
    exclusion_rules: {
      exclude_unsubscribed: document.getElementById('linkedinExcludeUnsubscribed')?.checked !== false,
      exclude_do_not_contact: document.getElementById('linkedinExcludeDnc')?.checked !== false,
      exclude_recently_contacted: document.getElementById('linkedinExcludeRecent')?.checked !== false,
      recent_days: 14,
      exclude_negative_responders: document.getElementById('linkedinExcludeNegative')?.checked !== false,
      exclude_sensitive_active: document.getElementById('linkedinExcludeSensitive')?.checked !== false
    }
  };
}

function setLinkedInCampaignStatus(message, type='success') {
  const status = document.getElementById('linkedinCampaignStatus');
  if (!status) return;
  status.className = `alert campaign-status active ${type}`;
  status.textContent = message;
}

async function previewLinkedInCampaignAudience() {
  const payload = getLinkedInCampaignPayload();
  const preview = document.getElementById('linkedinAudiencePreview');
  try {
    const res = await fetch('/api/communication/linkedin_campaign/preview', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(payload)
    });
    const data = await res.json();
    if (!res.ok || !data.ok) throw new Error(data.error || 'Unable to preview audience.');
    const excluded = Object.entries(data.excluded || {}).map(([key, count]) => `${key}: ${count}`).join(', ') || 'none';
    const sample = (data.sample || []).map(c => `${escapeHtml(c.candidate_name)} (${escapeHtml(c.email_addr)})`).join('<br>') || 'No eligible candidates found.';
    if (preview) {
      preview.style.display = 'block';
      preview.innerHTML = `<strong>${data.eligible_count}</strong> eligible candidates<br><span class="muted">Excluded: ${escapeHtml(excluded)}</span><div style="margin-top:8px">${sample}</div><div class="muted" style="margin-top:8px">Only this eligible set will be queued when you create the campaign.</div>`;
    }
    setLinkedInCampaignStatus(`Preview complete: ${data.eligible_count} eligible candidates.`, 'success');
  } catch (e) {
    setLinkedInCampaignStatus(e.message, 'error');
  }
}

async function createLinkedInCampaignDraft() {
  const payload = getLinkedInCampaignPayload();
  if (!valueOf('linkedinCampaignUrl').trim()) {
    setLinkedInCampaignStatus('LinkedIn company page URL is required before creating the draft.', 'error');
    return;
  }
  if (!valueOf('linkedinCampaignTracking').trim()) generateLinkedInTrackingLink();
  payload.tracking_link = valueOf('linkedinCampaignTracking').trim();
  try {
    const res = await fetch('/api/communication/linkedin_campaigns', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(payload)
    });
    const data = await res.json();
    if (!res.ok || !data.ok) throw new Error(data.error || 'Unable to create campaign.');
    window.currentLinkedInCampaignId = data.campaign_id;
    setLinkedInCampaignStatus(`${data.message} Campaign ID: ${data.campaign_id}`, 'success');
    document.getElementById('linkedinMetricSent').textContent = '0';
    document.getElementById('linkedinMetricClicks').textContent = '0';
  } catch (e) {
    setLinkedInCampaignStatus(e.message, 'error');
  }
}

async function sendDueLinkedInCampaignEmails() {
  if (!window.currentLinkedInCampaignId) {
    setLinkedInCampaignStatus('Create the campaign first, then send due emails.', 'error');
    return;
  }
  if (!confirm('Send all currently due LinkedIn Follow Campaign emails now? Future steps will remain scheduled for their day gaps.')) {
    return;
  }
  const btn = document.getElementById('linkedinSendDueBtn');
  if (btn) {
    btn.disabled = true;
    btn.textContent = 'Sending due emails...';
  }
  setLinkedInCampaignStatus('Sending due emails now. Please keep this page open...', 'success');
  try {
    const res = await fetch(`/api/communication/linkedin_campaigns/${window.currentLinkedInCampaignId}/send_due`, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({limit: 25})
    });
    const raw = await res.text();
    let data = {};
    try {
      data = raw ? JSON.parse(raw) : {};
    } catch (parseError) {
      throw new Error(raw ? raw.slice(0, 220) : 'Server returned an unreadable response.');
    }
    if (!res.ok || !data.ok) throw new Error(data.error || 'Unable to send due emails.');
    const analytics = data.analytics || {};
    document.getElementById('linkedinMetricSent').textContent = analytics.emails_sent || data.sent || 0;
    document.getElementById('linkedinMetricClicks').textContent = analytics.clicks_to_linkedin || 0;
    const errorText = (data.errors || []).map(e => `${e.recipient}: ${e.error}`).join(' | ');
    setLinkedInCampaignStatus(`Sent ${data.sent} due emails. Failed: ${data.failed}. Next emails remain scheduled by the selected day gaps.${errorText ? ' ' + errorText : ''}`, data.failed ? 'error' : 'success');
  } catch (e) {
    setLinkedInCampaignStatus(e.message, 'error');
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.textContent = 'Send Due Emails Now';
    }
  }
}

async function loadAtsApplicantPicklists() {
  try {
    const reqs = await getAtsRequirements();
    allRequirementOptions = reqs.filter(r => ['New', 'Open', 'In Progress'].includes(r.status || 'New'));
    renderRequirementOptions('acRequirement', allRequirementOptions);
  } catch(e) {
    console.error('Unable to load applicant picklists', e);
  }
}

function ensureAtsApplicantPicklists() {
  if (allRequirementOptions && allRequirementOptions.length) return;
  loadAtsApplicantPicklists();
}

function openAtsApplicantForm(mode='manual') {
  suppressWorkspaceAutoLoad = true;
  switchTab('ats-workspace');
  suppressWorkspaceAutoLoad = false;
  showAtsPage('atsApplicantForm');
  setTopNavActive('sourcing');
  showCandidateFormSection('personal');
  clearAddCandidateValidation();
  cvParsedData = null;
  currentRequirementChecks = [];
  ['acCandidateName','acEmail','acPhone','acCurrentCompany','acCurrentRoleTxt','acExperience','acSkillsSel','acNotice','acCurrentSalary','acExpectedSalary','acCurrentLocation','acPreferredLocation','acGraduationYear','acRemarks'].forEach(id => setValue(id, ''));
  const cvInput = document.getElementById('acCvFile');
  if (cvInput) cvInput.value = '';
  const parseStatus = document.getElementById('parseStatus');
  if (parseStatus) parseStatus.textContent = mode === 'parse' ? 'Choose a resume, then parse.' : '';
  currentRequirementChecks = [];
  setValue('acRequirement', '');
  setValue('acRequirementSearch', '');
  hideRequirementPicker();
  const reqHint = document.getElementById('acRequirementHint');
  if (reqHint) reqHint.textContent = 'Type at least 2 letters to search active requirements.';
}

function showCandidateFormSection(section) {
  document.querySelectorAll('[data-candidate-section]').forEach(step => {
    step.classList.toggle('active', step.dataset.candidateSection === section);
  });
  document.querySelectorAll('[data-candidate-form-section]').forEach(panel => {
    panel.classList.toggle('active', panel.dataset.candidateFormSection === section);
  });
}

function showAddCandidateModal() {
  openAtsApplicantForm('manual');
}

function addCustomField() {
  const label = valueOf('newCustomFieldLabel').trim();
  const type = valueOf('newCustomFieldType');
  if (!label) return;
  const wrap = document.getElementById('atsCustomFields');
  const div = document.createElement('div');
  div.className = type === 'checkbox' ? '' : 'form-group';
  div.innerHTML = type === 'checkbox'
    ? `<label><input type="checkbox" style="width:auto;margin-right:8px">${escapeHtml(label)}</label>`
    : `<label>${escapeHtml(label)}</label><input type="${type}">`;
  wrap.appendChild(div);
  setValue('newCustomFieldLabel', '');
}

let candidateSearchTimer = null;
let candidateListPage = 1;
const candidateListPageSize = 50;
let requirementListPage = 1;
const requirementListPageSize = 50;
let requirementListSearchTimer = null;

function candidateRowsFromResponse(payload) {
  return Array.isArray(payload) ? payload : (payload.rows || payload.candidates || []);
}

function renderPagination(targetId, meta, onPageFn) {
  const target = document.getElementById(targetId);
  if (!target) return;
  const page = Math.max(1, Number(meta.page || 1));
  const pageSize = Math.max(1, Number(meta.page_size || 50));
  const total = Math.max(0, Number(meta.total || 0));
  const totalPages = Math.max(1, Number(meta.total_pages || Math.ceil(total / pageSize) || 1));
  const start = total ? ((page - 1) * pageSize) + 1 : 0;
  const end = Math.min(total, page * pageSize);
  target.innerHTML = `
    <button onclick="${onPageFn}(${page - 1})" ${page <= 1 ? 'disabled' : ''}>Previous</button>
    <span>${start}-${end} of ${total}</span>
    <button onclick="${onPageFn}(${page + 1})" ${page >= totalPages ? 'disabled' : ''}>Next</button>
  `;
}

function goToCandidatePage(page) {
  candidateListPage = Math.max(1, page);
  loadDashboardCandidateList();
}

function loadCandidatesFirstPage() {
  candidateListPage = 1;
  loadDashboardCandidateList();
}

function goToRequirementPage(page) {
  requirementListPage = Math.max(1, page);
  loadRequirements();
}

function scheduleRequirementListSearch() {
  clearTimeout(requirementListSearchTimer);
  requirementListSearchTimer = setTimeout(() => {
    requirementListPage = 1;
    loadRequirements();
  }, 250);
}

function goToDashboardCandidatePage(page) {
  dashboardCandidatePage = Math.max(1, page);
  loadDashboardCandidateList();
}

function normalizeSearchExperience(value) {
  const text = String(value || '').trim();
  if (!text) return '';
  if (text.includes('-')) return text;
  const num = text.match(/\d+(\.\d+)?/);
  return num ? `${num[0]}-` : text;
}

function buildCandidateSearchParams() {
  const params = new URLSearchParams();
  params.set('page_size', '15');
  const query = valueOf('candidateSearchKeywords');
  const skills = valueOf('candidateSearchSkills');
  const client = valueOf('candidateSearchClient');
  const sourcer = valueOf('candidateSearchSourcer');
  const expRange = normalizeSearchExperience(valueOf('candidateSearchExperience'));
  const names = valueOf('candidateSearchNames');
  const phones = valueOf('candidateSearchPhones');
  const emails = valueOf('candidateSearchEmails');
  if (query) params.set('q', query);
  if (skills) params.set('skills', skills);
  if (client) params.set('client', client);
  if (sourcer) params.set('sender', sourcer.toLowerCase());
  if (expRange) params.set('exp_range', expRange);
  if (names) params.set('names', names);
  if (phones) params.set('phones', phones);
  if (emails) params.set('emails', emails);
  params.set('sort', 'newest');
  return params;
}

async function candidateRowsForSearch(query, location, extra = {}) {
  const params = new URLSearchParams();
  params.set('page_size', '15');
  if (query) params.set('q', query);
  if (location) params.set('location', location);
  if (extra.skills) params.set('skills', extra.skills);
  if (extra.client) params.set('client', extra.client);
  if (extra.expRange) params.set('exp_range', normalizeSearchExperience(extra.expRange));
  const res = await fetch('/api/candidates?' + params.toString());
  return candidateRowsFromResponse(await res.json());
}

function scheduleCandidateSearch() {
  clearTimeout(candidateSearchTimer);
  candidateSearchTimer = setTimeout(runCandidateSearch, 250);
}

async function runCandidateSearch() {
  const target = document.getElementById('candidateSearchResults');
  if (!target) return;
  target.innerHTML = '<div class="ats-panel pad">Searching candidates...</div>';
  try {
    const res = await fetch('/api/candidates?' + buildCandidateSearchParams().toString());
    if (!res.ok) throw new Error('Search failed');
    const rows = candidateRowsFromResponse(await res.json());
    renderSearchResults(target, rows);
  } catch(e) {
    target.innerHTML = '<div class="ats-panel pad">Unable to load search results.</div>';
  }
}

function exportCandidateSearchCsv() {
  const params = buildCandidateSearchParams();
  params.set('format', 'csv');
  window.location.href = '/api/candidates/export?' + params.toString();
}

function clearCandidateIdentityFilters() {
  ['candidateSearchNames', 'candidateSearchPhones', 'candidateSearchEmails'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.value = '';
  });
  scheduleCandidateSearch();
}

async function runPowerSearch() {
  const results = document.getElementById('powerSearchResults') || document.getElementById('candidateSearchResults');
  const terms = [valueOf('powerJobTitle'), valueOf('powerSkills'), valueOf('powerExperience'), valueOf('powerBoolean')].filter(Boolean).join(' ');
  if (results) {
    const rows = await candidateRowsForSearch(terms, valueOf('powerLocation'));
    renderSearchResults(results, rows);
  }
}

function renderSearchResults(target, rows) {
  const data = candidateRowsFromResponse(rows);
  if (!data.length) {
    const identityActive = ['candidateSearchNames', 'candidateSearchPhones', 'candidateSearchEmails'].some(id => {
      const el = document.getElementById(id);
      return el && String(el.value || '').trim();
    });
    target.innerHTML = '<div class="ats-panel pad">' + (identityActive
      ? 'No accessible candidates matched those names, phone numbers, or email IDs. If you are logged in as a recruiter, the search only shows candidates within your access scope.'
      : 'No candidates found.') + '</div>';
    return;
  }
  target.innerHTML = `<div class="muted" style="margin:0 0 10px 0">${data.length} candidate${data.length === 1 ? '' : 's'} found</div>
    <div class="candidates-table-wrap" style="display:block;max-height:620px;min-height:260px">
      <table class="candidates-table search-results-table">
        <thead><tr><th class="search-col-check"><input type="checkbox" onchange="toggleCandidateSearchSelection(this.checked)" title="Select all search results"></th><th class="search-col-name">Name</th><th class="search-col-role">Designation</th><th class="search-col-client">Client</th><th class="search-col-skills">Primary skills</th><th class="search-col-status">Status</th><th class="search-col-cv">Cv</th></tr></thead>
        <tbody>${data.map(c => `
          <tr onclick="openCandidateEditFromSearch(${c.id})">
            <td class="search-col-check" onclick="event.stopPropagation()"><input type="checkbox" class="candidate-search-checkbox" data-id="${c.id}"></td>
            <td class="search-col-name"><span class="candidate-name-link">${escapeHtml(c.candidate_name || '-')}</span><span class="candidate-subtext">${escapeHtml(c.email_addr || c.phone || '')}</span></td>
            <td class="search-col-role">${escapeHtml(c.current_role || 'Candidate')}<span class="candidate-subtext">${escapeHtml(formatExperienceLabel(c.experience_years))}</span></td>
            <td class="search-col-client">${escapeHtml(c.client_name || '-')}</td>
            <td class="search-col-skills"><span class="search-skill-text" title="${escapeHtml(c.key_skills || '')}">${escapeHtml(c.key_skills || '-')}</span></td>
            <td class="search-col-status"><span class="status ${statusClassName(c.status)}">${escapeHtml(c.status || 'New')}</span></td>
            <td class="search-col-cv" onclick="event.stopPropagation()">${c.cv_url ? `<a class="download-cv-btn" href="${escapeHtml(c.cv_url)}" title="Download CV" download>&#8681;</a>` : '-'}</td>
          </tr>`).join('')}</tbody>
      </table>
    </div>`;
}

function toggleCandidateSearchSelection(checked) {
  document.querySelectorAll('.candidate-search-checkbox').forEach(cb => { cb.checked = checked; });
}

function formatExperienceLabel(value) {
  const text = String(value || '').trim();
  if (!text) return '-';
  return /yr|year|exp/i.test(text) ? text : `${text} yrs exp`;
}

function openCandidateEditFromSearch(id) {
  showCandidateDetail(id);
  setTimeout(() => {
    const editBtn = document.getElementById('editCandidateFromDetailBtn');
    if (editBtn && editBtn.style.display !== 'none') editCandidateFromDetail();
  }, 450);
}

function candidateAiScreeningInfo(candidate) {
  const requirementId = String(candidate?.requirement_id || '').trim();
  if (!requirementId) {
    return {label: 'No JD attached', state: 'nojd'};
  }
  const status = String(candidate?.ai_screening_status || '').toLowerCase();
  const error = String(candidate?.ai_screening_error || '').trim();
  const score = candidate?.ai_screening_score;
  if (status === 'error' || error) {
    return {label: 'Error', state: 'error'};
  }
  if (score !== null && score !== undefined && String(score).trim() !== '') {
    const scoreNum = Number(score);
    return {label: `${Number.isFinite(scoreNum) ? scoreNum : score}%`, state: 'ok'};
  }
  if (status === 'pending') {
    return {label: 'Pending', state: 'pending'};
  }
  if (status === 'no_jd') {
    return {label: 'No JD attached', state: 'nojd'};
  }
  return {label: 'Pending', state: 'pending'};
}

function candidateAiScreeningReportLink(candidate) {
  const score = candidate?.ai_screening_score;
  const reportJson = String(candidate?.ai_screening_report_json || '').trim();
  const reportUrl = String(candidate?.ai_screening_report_url || '').trim();
  const requirementId = String(candidate?.requirement_id || '').trim();
  if (!requirementId) return '';
  if (!reportJson && (score === null || score === undefined || String(score).trim() === '') && !reportUrl) return '';
  return reportUrl || `/api/candidate/${candidate.id}/ai_screening_report`;
}

function candidateAiScreeningAction(candidate) {
  const requirementId = String(candidate?.requirement_id || '').trim();
  const status = String(candidate?.ai_screening_status || '').toLowerCase();
  const error = String(candidate?.ai_screening_error || '').trim();
  const isAdmin = Boolean(currentUser && currentUser.is_admin);
  const hasCv = Boolean(String(candidate?.cv_url || candidate?.cv_filename || '').trim());
  if (!requirementId) {
    return {label: 'No JD attached', state: 'nojd', disabled: true, title: 'Attach a requirement first'};
  }
  if (!hasCv) {
    return {label: 'No CV', state: 'nojd', disabled: true, title: 'Upload a CV before screening'};
  }
  if (status === 'pending') {
    return {label: 'Pending', state: 'pending', disabled: true, title: 'Screening is already running'};
  }
  if (status === 'error' || error) {
    return {label: 'Retry', state: 'error', disabled: false, title: 'Run screening again'};
  }
  if (candidate?.ai_screening_score !== null && candidate?.ai_screening_score !== undefined && String(candidate?.ai_screening_score).trim() !== '') {
    if (isAdmin) {
      return {label: 'Re-run', state: 'ok', disabled: false, title: 'Run screening again'};
    }
    return {label: 'Done', state: 'ok', disabled: true, title: 'AI screening already completed'};
  }
  return {label: 'Run', state: 'pending', disabled: false, title: 'Start AI screening'};
}

const dashboardColumns = [
  {key:'date', label:'Date', className:'dash-col-date', value:c => c.created_at ? c.created_at.split(' ')[0] : '-'},
  {key:'name', label:'Name', className:'dash-col-name', value:c => c.candidate_name || '-'},
  {key:'requirement', label:'Requirement', className:'dash-col-requirement', value:c => c.requirement_title || c.requirement_name || c.role_name || c.job_id || '-'},
  {key:'client', label:'Client', className:'dash-col-client', value:c => c.client_name || c.requirement_client || '-', pill:'pill-teal'},
  {key:'status', label:'Status', className:'dash-col-status', value:c => c.status || 'New'},
  {key:'ai_screening', label:'AI Screening', className:'dash-col-ai-screening', value:c => candidateAiScreeningInfo(c).label},
  {key:'ai_report', label:'Report', className:'dash-col-ai-report', value:c => candidateAiScreeningReportLink(c) ? 'Open' : '-'},
  {key:'ai_action', label:'Match', className:'dash-col-ai-action', value:c => candidateAiScreeningAction(c).label},
  {key:'recruiter', label:'Recruiter', className:'dash-col-recruiter', value:c => c.recruiter_name || 'Unassigned', pill:'pill-yellow'},
  {key:'communication', label:'Communication', className:'dash-col-actions', value:c => ''},
  {key:'role', label:'Designation', className:'dash-col-role', value:c => c.current_role || c.role_name || '-'},
  {key:'phone', label:'Phone', className:'dash-col-phone', value:c => c.phone || c.mobile || c.mobile_no || '-'},
  {key:'email', label:'Email', className:'dash-col-email', value:c => c.email_addr || c.email || '-'}
];
const dashboardColumnDefaultWidths = {date:128,name:260,requirement:240,client:140,status:190,ai_screening:160,ai_report:118,ai_action:148,recruiter:190,communication:210,role:170,phone:150,email:270};
let dashboardColumnWidths = JSON.parse(localStorage.getItem('hrguru_dashboard_column_widths') || '{}') || {};
const dashboardBackendFilterMap = {name:'name', requirement:'requirement', client:'client_like', status:'status', recruiter:'recruiter_name', role:'current_role', phone:'phone', email:'email', date:'created_at'};
const dashboardFilterFieldChoices = [
  {key:'date', label:'Date'},
  {key:'requirement', label:'Requirement'},
  {key:'client', label:'Client'},
  {key:'recruiter', label:'Recruiter'}
];
const dashboardBackendSortMap = {date:'date', name:'name', requirement:'requirement', client:'client', status:'status', recruiter:'recruiter', role:'role', phone:'phone', email:'email'};

function getDashboardColumn(key) {
  return dashboardColumns.find(col => col.key === key);
}

function dashboardColumnWidth(key) {
  const value = Number(dashboardColumnWidths[key] || dashboardColumnDefaultWidths[key] || 160);
  return Math.max(70, Math.min(520, value));
}

function dashboardColumnStyle(key) {
  const width = dashboardColumnWidth(key);
  return `width:${width}px;min-width:${width}px;max-width:${width}px`;
}

function dashboardCellValue(candidate, key) {
  const col = getDashboardColumn(key);
  return col ? String(col.value(candidate) || '') : '';
}

function visibleDashboardColumns() {
  dashboardViewState.hidden.requirement = false;
  dashboardViewState.hidden.ai_screening = false;
  dashboardViewState.hidden.ai_report = false;
  dashboardViewState.hidden.ai_action = false;
  dashboardViewState.hidden.client = false;
  dashboardViewState.hidden.status = false;
  dashboardViewState.hidden.recruiter = false;
  dashboardViewState.hidden.communication = false;
  return dashboardColumns.filter(col => col.key === 'communication' || !dashboardViewState.hidden[col.key]);
}

function dashboardFieldOptions(selected='') {
  return dashboardColumns
    .filter(col => col.key !== 'communication')
    .map(col => `<option value="${col.key}" ${selected === col.key ? 'selected' : ''}>${escapeHtml(col.label)}</option>`)
    .join('');
}

function dashboardFilterOptions(selected='') {
  return dashboardFilterFieldChoices.map(field => (
    `<option value="${field.key}" ${selected === field.key ? 'selected' : ''}>${escapeHtml(field.label)}</option>`
  )).join('');
}

function dashboardFilterEntries() {
  return Object.entries(dashboardViewState.filters).filter(([, value]) => String(value || '').trim());
}

function dashboardFilteredRows() {
  return [...dashboardRows];
}

function appendDashboardBackendParams(params) {
  const searchText = document.getElementById('searchInput')?.value.trim() || '';
  if (searchText) params.set('q', searchText);
  dashboardFilterEntries().forEach(([key, value]) => {
    const paramName = dashboardBackendFilterMap[key];
    if (paramName && String(value || '').trim()) params.set(paramName, String(value).trim());
  });
  const sortKey = dashboardBackendSortMap[dashboardViewState.sortBy || 'date'] || 'date';
  const sortDir = dashboardViewState.sortDir === 'asc' ? 'asc' : 'desc';
  params.set('sort', `${sortKey}_${sortDir}`);
}

function scheduleDashboardCandidateLoad() {
  clearTimeout(dashboardCandidateSearchTimer);
  dashboardCandidateSearchTimer = setTimeout(() => {
    dashboardCandidatePage = 1;
    loadDashboardCandidateList();
  }, 250);
}

function dashboardToolbarHtml(rowCount) {
  const filterCount = dashboardFilterEntries().length;
  const hiddenCount = Object.values(dashboardViewState.hidden).filter(Boolean).length;
  const deleteCount = dashboardSelectedDeleteCount();
  return `<div class="dashboard-candidate-toolbar">
    <div class="dashboard-candidate-toolbar-left">
      <span class="dashboard-view-name">Candidates List</span>
    </div>
    <div class="dashboard-candidate-toolbar-right">
      <button class="dashboard-tool ${hiddenCount ? 'active' : ''}" onclick="toggleDashboardPopover('fields')">Hide fields${hiddenCount ? ` (${hiddenCount})` : ''}</button>
      <button class="dashboard-tool ${filterCount ? 'active' : ''}" onclick="toggleDashboardPopover('filters')">Filter${filterCount ? ` (${filterCount})` : ''}</button>
      <button class="dashboard-tool ${dashboardViewState.groupBy ? 'active' : ''}" onclick="toggleDashboardPopover('group')">${dashboardViewState.groupBy ? `Grouped by ${escapeHtml(getDashboardColumn(dashboardViewState.groupBy)?.label || 'field')}` : 'Group'}</button>
      <button class="dashboard-tool active" onclick="toggleDashboardPopover('sort')">Sort</button>
      <button class="dashboard-tool" onclick="exportSelectedCandidates()">Export Selected</button>
      <button class="dashboard-tool danger" id="dashboardBulkDeleteBtn" onclick="deleteSelectedDashboardCandidates()" ${deleteCount ? '' : 'disabled style="opacity:.5;cursor:not-allowed"'}>Delete${deleteCount ? ` (${deleteCount})` : ''}</button>
      <button class="dashboard-tool" onclick="resetDashboardView()">Reset view</button>
    </div>
    <div class="dashboard-view-popover" id="dashboardViewPopover"></div>
  </div>`;
}

function dashboardTableHtml(rows) {
  const cols = visibleDashboardColumns();
  const tableWidth = 46 + cols.reduce((sum, col) => sum + dashboardColumnWidth(col.key), 0);
  const header = `<thead><tr><th class="dash-col-check"><input class="dashboard-check" type="checkbox" onclick="event.stopPropagation(); toggleDashboardSelectAll(this)"></th>${cols.map(col => `<th class="${col.className} dashboard-resizable" data-col-key="${col.key}" style="${dashboardColumnStyle(col.key)}">${escapeHtml(col.label)}<span class="dashboard-col-resizer" onmousedown="startDashboardColumnResize(event, '${col.key}')"></span></th>`).join('')}</tr></thead>`;
  const bodyRows = rows.map((c, index) => dashboardRowHtml(c, index, cols)).join('');
  return `<table class="candidates-table dashboard-candidate-table" style="width:${tableWidth}px;min-width:${tableWidth}px">${header}<tbody>${bodyRows || '<tr><td colspan="20" style="text-align:center;color:#8b95b5;padding:28px">No candidates match this view.</td></tr>'}</tbody></table>`;
}

function dashboardRowHtml(c, index, cols) {
  return `<tr onclick="showCandidateDetail(${c.id})">
    <td class="dash-col-check" onclick="event.stopPropagation()"><input class="dashboard-check dashboard-row-check" type="checkbox" value="${c.id}" onchange="updateDashboardDeleteButtonLabel()"></td>
    ${cols.map(col => dashboardCellHtml(c, col)).join('')}
  </tr>`;
}

function toggleDashboardSelectAll(checkbox) {
  document.querySelectorAll('#dashboardCandidateList .dashboard-row-check').forEach(input => {
    input.checked = checkbox.checked;
  });
  updateDashboardDeleteButtonLabel();
}

function dashboardSelectedDeleteCount() {
  return document.querySelectorAll('#dashboardCandidateList .dashboard-row-check:checked').length;
}

function updateDashboardDeleteButtonLabel() {
  const btn = document.getElementById('dashboardBulkDeleteBtn');
  if (!btn) return;
  const count = dashboardSelectedDeleteCount();
  btn.textContent = count ? `Delete (${count})` : 'Delete';
  btn.disabled = !count;
  btn.style.opacity = count ? '' : '.5';
  btn.style.cursor = count ? '' : 'not-allowed';
}

function dashboardCellHtml(c, col) {
  const widthStyle = dashboardColumnStyle(col.key);
  if (col.key === 'ai_screening') {
    const info = candidateAiScreeningInfo(c);
    return `<td class="${col.className}" style="${widthStyle}" onclick="event.stopPropagation()"><span class="ai-screening-badge ${info.state}">${escapeHtml(info.label)}</span></td>`;
  }
  if (col.key === 'ai_report') {
    const reportLink = candidateAiScreeningReportLink(c);
    if (!reportLink) {
      return `<td class="${col.className}" style="${widthStyle}" onclick="event.stopPropagation()">-</td>`;
    }
    return `<td class="${col.className}" style="${widthStyle}" onclick="event.stopPropagation()"><a class="action-btn" href="${escapeHtml(reportLink)}" target="_blank" rel="noopener" title="Open AI screening report">Open</a></td>`;
  }
  if (col.key === 'ai_action') {
    const action = candidateAiScreeningAction(c);
    if (action.disabled) {
      return `<td class="${col.className}" style="${widthStyle}" onclick="event.stopPropagation()"><span class="ai-screening-badge ${action.state}">${escapeHtml(action.label)}</span></td>`;
    }
    return `<td class="${col.className}" style="${widthStyle}" onclick="event.stopPropagation()"><button class="action-btn" title="${escapeHtml(action.title)}" onclick="event.stopPropagation(); triggerCandidateAiScreening(${c.id}, this)">${escapeHtml(action.label)}</button></td>`;
  }
  if (col.key === 'status') {
    return `<td class="${col.className}" style="${widthStyle}" onclick="event.stopPropagation()"><select class="status-select ${statusClassName(c.status)}" data-current-status="${escapeHtml(c.status || 'New')}" onchange="updateStatus(${c.id}, this.value, this)">${statusOptions(c.status || 'New')}</select></td>`;
  }
  if (col.key === 'communication') {
    return `<td class="${col.className}" style="${widthStyle}" onclick="event.stopPropagation()"><div class="dash-comm-actions"><button class="action-btn" onclick="openCandidateEmail(${c.id})">Email</button><button class="action-btn" onclick="openCandidateWhatsApp(${c.id})">WhatsApp</button></div></td>`;
  }
  if (col.key === 'cv') {
    const cvUrl = c.cv_url || '';
    const cvName = escapeHtml(c.cv_filename || 'Download CV');
    return `<td class="${col.className}" style="${widthStyle}" onclick="event.stopPropagation()">${cvUrl ? `<a class="dash-cv-link" href="${escapeHtml(cvUrl)}" title="${cvName}" download>Download</a>` : '-'}</td>`;
  }
  const value = escapeHtml(dashboardCellValue(c, col.key));
  if (col.key === 'name') return `<td class="${col.className}" style="${widthStyle}"><span class="candidate-name-link">${value}</span></td>`;
  if (col.pill) return `<td class="${col.className}" style="${widthStyle}"><span class="cell-pill ${col.pill}">${value}</span></td>`;
  return `<td class="${col.className}" style="${widthStyle}">${value}</td>`;
}

function renderDashboardCandidateList() {
  const target = document.getElementById('dashboardCandidateList');
  if (!target) return;
  localStorage.setItem('hrguru_dashboard_view_state', JSON.stringify(dashboardViewState));
  const rows = dashboardFilteredRows();
  const tableHtml = dashboardViewState.groupBy ? dashboardGroupedHtml(rows) : dashboardTableHtml(rows);
  target.innerHTML = dashboardToolbarHtml(rows.length) + '<div class="dashboard-x-scroll" id="dashboardTopScroller"><div class="dashboard-x-scroll-inner"></div></div><div class="dashboard-table-scroll" id="dashboardTableScroller">' + tableHtml + '</div><div class="table-pagination" id="dashboardCandidatePagination"></div>';
  syncDashboardScrollbars();
  renderPagination('dashboardCandidatePagination', dashboardCandidatePagination, 'goToDashboardCandidatePage');
  updateDashboardDeleteButtonLabel();
}

function syncDashboardScrollbars() {
  const topScroller = document.getElementById('dashboardTopScroller');
  const tableScroller = document.getElementById('dashboardTableScroller');
  if (!topScroller || !tableScroller) return;
  const table = tableScroller.querySelector('.dashboard-candidate-table');
  const inner = topScroller.querySelector('.dashboard-x-scroll-inner');
  if (table && inner) inner.style.width = table.offsetWidth + 'px';
  let syncing = false;
  topScroller.onscroll = () => {
    if (syncing) return;
    syncing = true;
    tableScroller.scrollLeft = topScroller.scrollLeft;
    syncing = false;
  };
  tableScroller.onscroll = () => {
    if (syncing) return;
    syncing = true;
    topScroller.scrollLeft = tableScroller.scrollLeft;
    syncing = false;
  };
}

function startDashboardColumnResize(event, key) {
  event.preventDefault();
  event.stopPropagation();
  const startX = event.clientX;
  const startWidth = dashboardColumnWidth(key);
  const minWidth = key === 'cv' ? 90 : 80;
  document.body.classList.add('dashboard-resizing');
  const onMove = moveEvent => {
    const nextWidth = Math.max(minWidth, Math.min(560, startWidth + moveEvent.clientX - startX));
    dashboardColumnWidths[key] = nextWidth;
    document.querySelectorAll(`#dashboardCandidateList [data-col-key="${key}"], #dashboardCandidateList .${getDashboardColumn(key)?.className || ''}`).forEach(cell => {
      cell.style.width = nextWidth + 'px';
      cell.style.minWidth = nextWidth + 'px';
      cell.style.maxWidth = nextWidth + 'px';
    });
    const cols = visibleDashboardColumns();
    const tableWidth = 46 + cols.reduce((sum, col) => sum + dashboardColumnWidth(col.key), 0);
    document.querySelectorAll('#dashboardCandidateList .dashboard-candidate-table').forEach(table => {
      table.style.width = tableWidth + 'px';
      table.style.minWidth = tableWidth + 'px';
    });
    const inner = document.querySelector('#dashboardTopScroller .dashboard-x-scroll-inner');
    if (inner) inner.style.width = tableWidth + 'px';
  };
  const onUp = () => {
    localStorage.setItem('hrguru_dashboard_column_widths', JSON.stringify(dashboardColumnWidths));
    document.body.classList.remove('dashboard-resizing');
    document.removeEventListener('mousemove', onMove);
    document.removeEventListener('mouseup', onUp);
  };
  document.addEventListener('mousemove', onMove);
  document.addEventListener('mouseup', onUp);
}

function dashboardGroupedHtml(rows) {
  const key = dashboardViewState.groupBy;
  const groups = {};
  rows.forEach(row => {
    const label = dashboardCellValue(row, key) || '(Empty)';
    if (!groups[label]) groups[label] = [];
    groups[label].push(row);
  });
  return Object.entries(groups)
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([label, groupRows]) => `<div class="dashboard-count-row"><span>${escapeHtml(getDashboardColumn(key)?.label || 'Group')}</span><strong>${escapeHtml(label)}</strong><span>${groupRows.length}</span></div>${dashboardTableHtml(groupRows)}`)
    .join('') || dashboardTableHtml([]);
}

function toggleDashboardPopover(type) {
  const popover = document.getElementById('dashboardViewPopover');
  if (!popover) return;
  if (popover.dataset.type === type && popover.classList.contains('active')) {
    popover.classList.remove('active');
    return;
  }
  popover.dataset.type = type;
  popover.innerHTML = dashboardPopoverHtml(type);
  popover.classList.add('active');
}

function dashboardPopoverHtml(type) {
  if (type === 'filters') {
    const entries = (dashboardViewState.filterDrafts && dashboardViewState.filterDrafts.length) ? dashboardViewState.filterDrafts : dashboardFilterEntries();
    return `<h3>Filter records</h3>
      <div class="dashboard-filter-list" id="dashboardFilterList">
        ${(entries.length ? entries : [['date', '']]).map(([key, value]) => dashboardFilterRowHtml(key, value)).join('')}
      </div>
      <div style="display:flex;gap:8px;margin-top:10px;justify-content:space-between">
        <button class="dashboard-tool active" onclick="addDashboardFilterRow()">Add filter</button>
        <button class="dashboard-tool active" onclick="applyDashboardFilters()">Apply filters</button>
        <button class="dashboard-tool" onclick="clearDashboardFilters()">Clear filters</button>
      </div>`;
  }
  if (type === 'group') {
    return `<h3>Group records</h3>
      <div class="dashboard-control-grid">
        <label>Group by</label>
        <select onchange="setDashboardGroupBy(this.value)"><option value="">No grouping</option>${dashboardFieldOptions(dashboardViewState.groupBy)}</select>
        <button class="dashboard-tool" onclick="setDashboardGroupBy('')">Clear</button>
      </div>`;
  }
  if (type === 'sort') {
    return `<div class="popover-head"><h3>Sort records</h3><button class="popover-close" type="button" onclick="closeReportingViewPopover()">x</button></div>
      <div class="dashboard-control-grid">
        <label>Sort by</label>
        <select onchange="setDashboardSort(this.value, dashboardViewState.sortDir)">${dashboardFieldOptions(dashboardViewState.sortBy)}</select>
        <select onchange="setDashboardSort(dashboardViewState.sortBy, this.value)"><option value="asc" ${dashboardViewState.sortDir === 'asc' ? 'selected' : ''}>Ascending</option><option value="desc" ${dashboardViewState.sortDir === 'desc' ? 'selected' : ''}>Descending</option></select>
      </div>`;
  }
  return `<h3>Hide fields</h3>
    <div class="dashboard-field-list">
      ${dashboardColumns.map(col => {
        const locked = ['requirement', 'client', 'status', 'recruiter', 'communication'].includes(col.key);
        return `<label><input type="checkbox" ${locked || !dashboardViewState.hidden[col.key] ? 'checked' : ''} ${locked ? 'disabled' : ''} onchange="setDashboardFieldVisible('${col.key}', this.checked)"> ${escapeHtml(col.label)}</label>`;
      }).join('')}
    </div>`;
}

function dashboardFilterRowHtml(key, value) {
  return `<div class="dashboard-filter-row">
    <select onchange="updateDashboardFilterField(this)">${dashboardFilterOptions(key)}</select>
    <input value="${escapeHtml(value)}" placeholder="Contains..." oninput="updateDashboardFilterValue(this)">
    <button class="dashboard-tool" onclick="removeDashboardFilterRow(this)">Remove</button>
  </div>`;
}

function readDashboardFilterRows() {
  const filters = {};
  const drafts = [];
  document.querySelectorAll('#dashboardFilterList .dashboard-filter-row').forEach(row => {
    const key = row.querySelector('select')?.value || '';
    const value = row.querySelector('input')?.value || '';
    if (key) drafts.push([key, value]);
    if (key && value.trim()) filters[key] = value.trim();
  });
  dashboardViewState.filters = filters;
  dashboardViewState.filterDrafts = drafts.length ? drafts : [['date', '']];
}

function updateDashboardFilterField(select) {
  readDashboardFilterRows();
}

function updateDashboardFilterValue(input) {
  readDashboardFilterRows();
}

function addDashboardFilterRow() {
  const list = document.getElementById('dashboardFilterList');
  if (!list) return;
  list.insertAdjacentHTML('beforeend', dashboardFilterRowHtml('date', ''));
  readDashboardFilterRows();
}

function removeDashboardFilterRow(button) {
  button.closest('.dashboard-filter-row')?.remove();
  readDashboardFilterRows();
  dashboardCandidatePage = 1;
  loadDashboardCandidateList();
  toggleDashboardPopover('filters');
}

function clearDashboardFilters() {
  dashboardViewState.filters = {};
  dashboardViewState.filterDrafts = [['date', '']];
  dashboardCandidatePage = 1;
  loadDashboardCandidateList();
  toggleDashboardPopover('filters');
}

function applyDashboardFilters() {
  readDashboardFilterRows();
  dashboardCandidatePage = 1;
  loadDashboardCandidateList();
}

function setDashboardGroupBy(key) {
  dashboardViewState.groupBy = key;
  renderDashboardCandidateList();
}

function setDashboardSort(key, dir) {
  dashboardViewState.sortBy = key || 'date';
  dashboardViewState.sortDir = dir || 'asc';
  dashboardCandidatePage = 1;
  loadDashboardCandidateList();
}

function setDashboardFieldVisible(key, visible) {
  if (['requirement', 'client', 'status', 'recruiter', 'communication'].includes(key)) {
    dashboardViewState.hidden[key] = false;
    renderDashboardCandidateList();
    return;
  }
  dashboardViewState.hidden[key] = !visible;
  renderDashboardCandidateList();
  toggleDashboardPopover('fields');
}

function resetDashboardView() {
  dashboardViewState = {groupBy:'', sortBy:'date', sortDir:'desc', filters:{}, filterDrafts:[['name', '']], hidden:{role:true, phone:true, email:true}};
  dashboardCandidatePage = 1;
  loadDashboardCandidateList();
}

async function loadDashboardCandidateList() {
  const target = document.getElementById('dashboardCandidateList');
  if (!target) return;
  target.innerHTML = '<div class="dashboard-candidate-toolbar"><div class="dashboard-candidate-toolbar-left"><span class="dashboard-view-name">Candidates List</span></div></div><table class="candidates-table"><tbody><tr><td style="text-align:center;color:#6b7494;padding:28px">Loading candidates...</td></tr></tbody></table>';
  try {
    const params = new URLSearchParams();
    params.set('page', String(dashboardCandidatePage));
    params.set('page_size', String(dashboardCandidatePageSize));
    appendDashboardBackendParams(params);
    const res = await fetch('/api/candidates?' + params.toString());
    if (!res.ok) throw new Error('Candidate list request failed: ' + res.status);
    const payload = await res.json();
    const data = candidateRowsFromResponse(payload);
    dashboardCandidatePagination = Array.isArray(payload)
      ? {page:1,page_size:data.length || dashboardCandidatePageSize,total:data.length,total_pages:1}
      : payload;
    if (!data.length && dashboardCandidatePagination.total && dashboardCandidatePage > 1) {
      dashboardCandidatePage = Math.max(1, Number(dashboardCandidatePagination.total_pages || 1));
      return loadDashboardCandidateList();
    }
    dashboardRows = data;
    renderDashboardCandidateList();
    renderActiveFilterChips();
  } catch(e) {
    console.error('Unable to load dashboard candidate list', e);
    target.innerHTML = '<table class="candidates-table"><tbody><tr><td style="text-align:center;color:#e86a6a;padding:28px">Unable to load candidates.</td></tr></tbody></table>';
  }
}

function getCachedDashboardCandidate(id) {
  const idStr = String(id || '');
  if (!idStr) return null;
  return (dashboardRows || []).find(row => String(row.id || '') === idStr) || null;
}

function renderCandidateDetail(c) {
  window.currentCandidate = c;
  document.getElementById('detailName').textContent = c.candidate_name || '-';
  document.getElementById('detailEmail').textContent = c.email_addr || '-';
  document.getElementById('detailPhone').textContent = c.phone || '-';
  document.getElementById('detailCompany').textContent = c.current_company || '-';
  document.getElementById('detailRole').textContent = c.current_role || '-';
  const requirementLabel = [c.requirement_title || c.role_name || '', c.client_name || ''].filter(Boolean).join(' - ') || '-';
  document.getElementById('detailRequirement').textContent = requirementLabel;
  const screeningInfo = candidateAiScreeningInfo(c);
  document.getElementById('detailAiScreening').innerHTML = `<span class="ai-screening-badge ${screeningInfo.state}">${escapeHtml(screeningInfo.label)}</span>`;
  const reportLink = candidateAiScreeningReportLink(c);
  document.getElementById('detailAiReport').innerHTML = reportLink
    ? `<a href="${escapeHtml(reportLink)}" target="_blank" rel="noopener">Open Report</a>`
    : '-';
  document.getElementById('detailExp').textContent = c.experience_years || '-';
  document.getElementById('detailSkills').textContent = c.key_skills || '-';
  document.getElementById('detailStatus').textContent = c.status || 'New';
  document.getElementById('detailRecruiter').textContent = c.recruiter_name || '-';
  document.getElementById('detailSource').textContent = c.source || '-';
  document.getElementById('detailNotice').textContent = c.notice_period || '-';
  document.getElementById('detailSalary').textContent = (c.current_salary || '-') + ' / ' + (c.expected_salary || '-');
  document.getElementById('detailLocation').textContent = c.current_location || '-';
  document.getElementById('detailCvLink').innerHTML = c.cv_url
    ? `<a href="${escapeHtml(c.cv_url)}" target="_blank">${escapeHtml(c.cv_filename || 'View CV')}</a>`
    : (c.cv_filename || '-');
  document.getElementById('detailAdded').textContent = c.created_at ? c.created_at.split(' ')[0] : '-';
  document.getElementById('detailFeedback').textContent = c.candidate_feedback || '-';
  const screeningAction = candidateAiScreeningAction(c);
  const aiBtn = document.getElementById('runAiScreeningBtn');
  if (aiBtn) {
    aiBtn.textContent = screeningAction.label === 'Re-run'
      ? 'Re-run AI Screening'
      : (screeningAction.label === 'Done' ? 'AI Screening Complete' : 'Run AI Screening');
    aiBtn.disabled = Boolean(screeningAction.disabled);
    aiBtn.title = screeningAction.title || '';
  }
  setValue('editCandName', c.candidate_name);
  setValue('editCandEmail', c.email_addr);
  setValue('editCandPhone', c.phone);
  setValue('editCandCompany', c.current_company);
  setValue('editCandRoleTxt', c.current_role);
  setValue('editCandExp', c.experience_years);
  setValue('editCandSkills', c.key_skills);
  setValue('editCandSkillsText', c.key_skills);
  setValue('editCandLocation', c.current_location);
  setValue('editCandCurrSal', c.current_salary);
  setValue('editCandExpSal', c.expected_salary);
  setValue('editCandNotice', c.notice_period);
  setValue('editCandRemarks', c.remarks);
  const editCvFile = document.getElementById('editCandCvFile');
  if (editCvFile) editCvFile.value = '';
  const editCvStatus = document.getElementById('editCandCvStatus');
  if (editCvStatus) editCvStatus.textContent = c.cv_filename ? `Current CV: ${c.cv_filename}` : 'No CV uploaded yet.';
  const editStatus = document.getElementById('editCandStatus');
  if (editStatus) editStatus.innerHTML = statusOptions(c.status || 'New');
  setValue('editCandStatus', c.status || 'New');
  const isAdmin = Boolean(currentUser && currentUser.is_admin);
  const owner = c.sourcer_id === (currentUser && currentUser.team_member_id) ||
    String(c.recruiter_email || '').toLowerCase() === String(currentUser.recruiter_email || currentUser.email || '').toLowerCase();
  const canEdit = isAdmin || owner;
  const editBtn = document.getElementById('editCandidateFromDetailBtn');
  if (editBtn) editBtn.style.display = canEdit ? '' : 'none';
  document.getElementById('candidateDetailContent').style.display = 'block';
  document.getElementById('candidateEditForm').style.display = 'none';
  document.getElementById('cdActions').style.display = 'flex';
  document.getElementById('editActions').style.display = 'none';
  document.getElementById('candidateDetailModal').classList.remove('active');
  setTimeout(() => {
    document.getElementById('candidateDetailModal').classList.add('active');
  }, 10);
}

function canDeleteCandidate(candidate) {
  if (!candidate) return false;
  if (currentUser && currentUser.is_admin) return true;
  const currentTeamId = String((currentUser && currentUser.team_member_id) || '');
  const candidateOwnerId = String(candidate.sourcer_id || '');
  const currentEmail = String((currentUser && (currentUser.recruiter_email || currentUser.email)) || '').toLowerCase();
  const candidateEmail = String(candidate.recruiter_email || '').toLowerCase();
  return Boolean(
    (currentTeamId && candidateOwnerId && currentTeamId === candidateOwnerId) ||
    (currentEmail && candidateEmail && currentEmail === candidateEmail)
  );
}

async function deleteDashboardCandidate(id, name) {
  const ok = await confirmAction({
    title: 'Delete candidate?',
    message: `Delete ${name || 'this candidate'} from the candidate list?`,
    okText: 'Delete'
  });
  if (!ok) return;
  const res = await fetch('/api/candidate/' + id, {method:'DELETE'});
  const data = await res.json().catch(() => ({}));
  if (res.ok && data.ok !== false) {
    showToast('Candidate deleted', 'success');
    loadDashboardCandidateList();
  } else {
    showToast(data.error || 'Unable to delete candidate', 'error');
  }
}

async function deleteSelectedDashboardCandidates() {
  const selectedIds = Array.from(document.querySelectorAll('#dashboardCandidateList .dashboard-row-check:checked'))
    .map(input => input.value)
    .filter(Boolean);
  if (!selectedIds.length) {
    showToast('Select candidates first', 'error');
    return;
  }
  const ok = await confirmAction({
    title: 'Delete selected candidates?',
    message: `Delete ${selectedIds.length} selected candidate${selectedIds.length === 1 ? '' : 's'} from the candidate list?`,
    okText: 'Delete'
  });
  if (!ok) return;

  let deleted = 0;
  let failed = 0;
  for (const id of selectedIds) {
    try {
      const res = await fetch('/api/candidate/' + id, {method:'DELETE'});
      const data = await res.json().catch(() => ({}));
      if (res.ok && data.ok !== false) deleted += 1;
      else failed += 1;
    } catch (e) {
      failed += 1;
    }
  }

  if (deleted) {
    showToast(`Deleted ${deleted} candidate${deleted === 1 ? '' : 's'}${failed ? `, ${failed} failed` : ''}`, failed ? 'error' : 'success');
    loadDashboardCandidateList();
    loadCandidateStats();
  } else {
    showToast('Unable to delete selected candidates', 'error');
  }
}

/* currentUser is initialized via initCurrentUser; single source of truth */

async function initCurrentUser() {
  try {
    const res = await fetch('/api/me');
    if (res.ok) {
      currentUser = await res.json();
      localStorage.setItem('hrguru_user', JSON.stringify(currentUser));
    }
  } catch(e) {
    const stored = localStorage.getItem('hrguru_user');
    if (stored) {
      try { currentUser = JSON.parse(stored); } catch(err) { console.error('Failed to parse user data', err); }
    }
  }
  
  // Keep only the profile menu in the top navigation.
  try {
    const profileBtn = document.getElementById('profileMenuBtn');
    if (profileBtn) {
      profileBtn.textContent = String(currentUser.username || 'U').trim().slice(0, 1).toUpperCase() || 'U';
    }
  } catch(e) { console.log('headerUserInfo error:', e); }
  
  // Update logout button with username
  try {
    const stored = localStorage.getItem('hrguru_user');
    const user = stored ? JSON.parse(stored) : {username: 'User'};
    const logoutBtn = document.getElementById('logoutBtn');
    if (logoutBtn) logoutBtn.textContent = 'Logout ' + (user.username || 'User');
  } catch(e) { console.log('logout update error:', e); }
  
  updateNavForRole();
  renderProfileMenuState();
  const dailyReportOption = document.querySelector('#reportType option[value="daily_dashboard"]');
  const reportType = document.getElementById('reportType');
  if (dailyReportOption && !currentUser.is_admin) {
    dailyReportOption.remove();
    if (reportType && reportType.value === 'daily_dashboard') reportType.value = 'sourcer';
  }
  currentUser.loaded = true;
}

function updateNavForRole() {
  const bulkUploadNav = document.getElementById('nav-bulk-upload');
  const userManagementNav = document.getElementById('nav-user-management');
  const roleName = String((currentUser && currentUser.role) || '').toLowerCase();
  const hasFullWorkspace = Boolean(
    currentUser && (
      currentUser.is_admin ||
      roleName.includes('admin') ||
      roleName.includes('power') ||
      roleName.includes('lead') ||
      roleName.includes('manager')
    )
  );
  document.body.classList.toggle('recruiter-lean', !hasFullWorkspace);
  document.querySelectorAll('.topnav-link.admin-only').forEach(link => {
    link.style.display = currentUser.is_admin ? 'flex' : 'none';
  });
  document.querySelectorAll('.daily-only').forEach(section => {
    section.style.display = hasFullWorkspace ? 'none' : '';
  });
  document.querySelectorAll('.advanced-only').forEach(section => {
    section.style.display = hasFullWorkspace ? '' : 'none';
  });
  document.querySelectorAll('.bulk-upload-only').forEach(section => {
    if (!currentUser.can_bulk_upload) {
      section.style.display = 'none';
    } else if (section.classList.contains('topnav-link')) {
      section.style.display = 'flex';
    } else if (section.classList.contains('topnav-action-btn')) {
      section.style.display = 'inline-flex';
    } else {
      section.style.display = '';
    }
  });
  document.querySelectorAll('.admin-setup-only').forEach(section => {
    section.style.display = currentUser.is_admin ? '' : 'none';
  });

  if (bulkUploadNav) {
    bulkUploadNav.style.display = currentUser.can_bulk_upload ? '' : 'none';
  }
  if (userManagementNav) {
    userManagementNav.style.display = currentUser.is_admin ? '' : 'none';
  }
}

function toggleProfileMenu() {
  const menu = document.getElementById('profileDropdown');
  if (menu) menu.classList.toggle('active');
}

function closeProfileMenu() {
  const menu = document.getElementById('profileDropdown');
  if (menu) menu.classList.remove('active');
}

function renderProfileMenuState() {
  const switchBtn = document.getElementById('profileSwitchBtn');
  const restoreBtn = document.getElementById('profileRestoreBtn');
  const banner = document.getElementById('impersonationBanner');
  const bannerText = document.getElementById('impersonationBannerText');
  const impersonating = Boolean(currentUser && currentUser.impersonation_active);
  const canSwitch = Boolean(currentUser && currentUser.is_admin && !impersonating);
  if (switchBtn) switchBtn.style.display = canSwitch ? 'block' : 'none';
  if (restoreBtn) restoreBtn.style.display = impersonating ? 'block' : 'none';
  if (banner) banner.style.display = impersonating ? 'flex' : 'none';
  if (bannerText) {
    if (impersonating) {
      bannerText.textContent = `Switched profile mode: viewing as ${currentUser.username || currentUser.recruiter_name || 'another team member'}.`;
    } else {
      bannerText.textContent = '';
    }
  }
}

function setSwitchProfileAlert(message, type='error') {
  const alertBox = document.getElementById('switchProfileAlert');
  if (!alertBox) return;
  alertBox.textContent = message || '';
  alertBox.style.display = message ? 'block' : 'none';
  alertBox.style.background = type === 'success' ? '#1f3a2a' : '#4a2b2b';
  alertBox.style.color = type === 'success' ? '#b7f0c6' : '#ffb3b3';
}

function filterSwitchProfileOptions() {
  const select = document.getElementById('switchProfileSelect');
  const query = String(document.getElementById('switchProfileSearch')?.value || '').trim().toLowerCase();
  if (!select) return;
  const options = Array.from(select.options || []);
  options.forEach(option => {
    const text = String(option.dataset.searchText || option.textContent || '').toLowerCase();
    option.hidden = query ? !text.includes(query) : false;
  });
}

async function openSwitchProfileModal() {
  if (!currentUser || !currentUser.is_admin || currentUser.impersonation_active) {
    showToast('Switch profile is available only from the admin profile.', 'error');
    return;
  }
  const modal = document.getElementById('switchProfileModal');
  const select = document.getElementById('switchProfileSelect');
  const search = document.getElementById('switchProfileSearch');
  if (!modal || !select) return;
  setSwitchProfileAlert('');
  select.innerHTML = '<option value="">Loading team members...</option>';
  if (search) search.value = '';
  showModal('switchProfileModal');
  try {
    const rows = await getAtsTeamRows();
    const currentId = String(currentUser.team_member_id || '');
    const filtered = (rows || []).filter(r => String(r.id) !== currentId);
    if (!filtered.length) {
      select.innerHTML = '<option value="">No alternate team members available.</option>';
      return;
    }
    select.innerHTML = filtered.map(r => {
      const name = escapeHtml(r.name || '');
      const email = escapeHtml(r.email || '');
      const role = escapeHtml(r.role || '');
      const searchText = `${r.name || ''} ${r.email || ''} ${r.role || ''}`.trim().toLowerCase();
      return `<option value="${r.id}" data-search-text="${escapeHtml(searchText)}">${name}${email ? ' · ' + email : ''}${role ? ' · ' + role : ''}</option>`;
    }).join('');
    filterSwitchProfileOptions();
  } catch (e) {
    select.innerHTML = '<option value="">Unable to load team members.</option>';
    setSwitchProfileAlert(e.message || 'Unable to load team members.');
  }
}

async function applySwitchProfile() {
  const select = document.getElementById('switchProfileSelect');
  const teamMemberId = Number(select?.value || 0);
  if (!teamMemberId) {
    setSwitchProfileAlert('Please select a team member first.');
    return;
  }
  setSwitchProfileAlert('');
  const btn = document.querySelector('#switchProfileModal .btn:not(.btn-outline)[type="button"]');
  if (btn) {
    btn.disabled = true;
    btn.textContent = 'Switching...';
  }
  try {
    const res = await fetch('/api/admin/switch-profile', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({team_member_id: teamMemberId})
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok || data.error) throw new Error(data.error || 'Unable to switch profile.');
    closeModal('switchProfileModal');
    showToast('Profile switched successfully.', 'success');
    window.location.href = '/';
  } catch (e) {
    setSwitchProfileAlert(e.message || 'Unable to switch profile.');
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.textContent = 'Switch Profile';
    }
  }
}

async function restoreAdminProfile() {
  setSwitchProfileAlert('');
  try {
    const res = await fetch('/api/admin/switch-profile', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({action: 'restore'})
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok || data.error) throw new Error(data.error || 'Unable to restore admin profile.');
    closeProfileMenu();
    closeModal('switchProfileModal');
    showToast('Returned to admin profile.', 'success');
    window.location.href = '/';
  } catch (e) {
    showToast(e.message || 'Unable to restore admin profile.', 'error');
  }
}

function setProfileAlert(message, type='error') {
  const alertBox = document.getElementById('profileAlert');
  if (!alertBox) return;
  alertBox.textContent = message || '';
  alertBox.style.display = message ? 'block' : 'none';
  alertBox.style.background = type === 'success' ? '#1f3a2a' : '#4a2b2b';
  alertBox.style.color = type === 'success' ? '#b7f0c6' : '#ffb3b3';
}

function applyProfileData(user) {
  setValue('profileName', user.username || user.recruiter_name || '');
  setValue('profileEmail', user.email || user.recruiter_email || '');
  setValue('profilePhone', user.phone || '');
  setValue('profileRole', user.role || (user.is_admin ? 'Admin' : 'Recruiter'));
  setValue('profileNotes', user.notes || '');
}

function setProfileActionState(saved=false) {
  const cancelBtn = document.getElementById('profileCancelBtn');
  if (!cancelBtn) return;
  cancelBtn.textContent = saved ? 'Close' : 'Cancel';
  cancelBtn.dataset.saved = saved ? '1' : '0';
}

async function loadProfilePage() {
  setProfileAlert('');
  setProfileActionState(false);
  try {
    const res = await fetch('/api/me');
    if (!res.ok) throw new Error('Unable to load profile.');
    currentUser = await res.json();
    localStorage.setItem('hrguru_user', JSON.stringify(currentUser));
  } catch(e) {
    setProfileAlert(e.message || 'Unable to load profile.');
  }
  applyProfileData(currentUser || {});
}

function cancelProfileEdit() {
  const saved = document.getElementById('profileCancelBtn')?.dataset.saved === '1';
  if (!saved) {
    applyProfileData(currentUser || {});
    setProfileAlert('');
  }
  setProfileActionState(false);
  switchTab('ats-workspace');
}

async function saveProfilePage() {
  const name = valueOf('profileName').trim();
  const email = valueOf('profileEmail').trim();
  const phone = valueOf('profilePhone').trim();
  const notes = valueOf('profileNotes').trim();
  if (!name) {
    setProfileAlert('Name is required.');
    return;
  }
  if (email && !validEmailAddress(email)) {
    setProfileAlert('Please enter a valid email address.');
    return;
  }
  const btn = document.getElementById('profileSaveBtn');
  if (btn) {
    btn.disabled = true;
    btn.textContent = 'Saving...';
  }
  try {
    const res = await fetch('/api/me', {
      method:'PATCH',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({name, email, phone, notes})
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok || data.error) throw new Error(data.error || 'Unable to save profile.');
    currentUser = data.user || currentUser;
    localStorage.setItem('hrguru_user', JSON.stringify(currentUser));
    applyProfileData(currentUser);
    const profileBtn = document.getElementById('profileMenuBtn');
    if (profileBtn) profileBtn.textContent = String(currentUser.username || 'U').trim().slice(0, 1).toUpperCase() || 'U';
    renderProfileMenuState();
    setProfileAlert('Profile updated successfully.', 'success');
    setProfileActionState(true);
    showToast('Profile updated successfully.', 'success');
  } catch(e) {
    setProfileAlert(e.message || 'Unable to save profile.');
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.textContent = 'Save Profile';
    }
  }
}

document.addEventListener('DOMContentLoaded', async function() {
  await initCurrentUser();
  const columnMenu = document.querySelector('.column-menu');
  if (columnMenu) {
    columnMenu.addEventListener('click', function(e) { e.stopPropagation(); });
  }
  document.addEventListener('click', function() {
    const panel = document.getElementById('columnPanel');
    if (panel) panel.classList.remove('active');
    document.getElementById('reqTitleSuggestionMenu')?.classList.remove('active');
    closeProfileMenu();
    document.getElementById('reqStatusMenu')?.classList.remove('active');
  });
  document.getElementById('reqTitle')?.addEventListener('click', function(e) { e.stopPropagation(); });
  document.getElementById('reqTitleSuggestionMenu')?.addEventListener('click', function(e) { e.stopPropagation(); });
  document.getElementById('reqJdFile')?.addEventListener('change', function() {
    const status = document.getElementById('reqJdStatus');
    if (status) status.textContent = this.files && this.files[0] ? this.files[0].name : 'No JD uploaded.';
  });
  const profileMenu = document.querySelector('.profile-menu');
  if (profileMenu) profileMenu.addEventListener('click', function(e) { e.stopPropagation(); });
  
  document.querySelectorAll('.tab-link').forEach(link => {
    link.addEventListener('click', function(e) {
      const tab = this.dataset.tab;
      if (!tab) return;
      e.preventDefault();
      if (this.id === 'nav-bulk-upload') {
        window.location.href = '/upload/instructions';
        return;
      }
      switchTab(tab);
    });
  });
  
  loadRecruiterDashboardSummary({light:true, deferFull:true});
  markTabDataLoaded('ats-workspace');
  hideReportingDateFilters();
  handleInitialAppHash();
});

async function loadRecruiters(selectId = 'acRecruiter', selectedId = '') {
  console.log("loadRecruiters called for:", selectId);

  try {
    const rows = await getAtsTeamRows();

    const sel = document.getElementById(selectId);
    if (!sel) return;

    sel.innerHTML = '<option value="">Select Recruiter...</option>';

    rows.forEach(r => {
      sel.innerHTML += `<option value="${r.id}">${r.name}</option>`;
    });

    if (selectedId) {
      sel.value = selectedId;
    }

  } catch(e) {
    console.error('Failed to load recruiters', e);
  }
}

async function getAtsSkills() {
  if (!atsReferenceCache.skills) {
    atsReferenceCache.skills = fetch('/api/skills').then(r => r.json());
  }
  return atsReferenceCache.skills;
}

async function getAtsRequirements() {
  if (!atsReferenceCache.requirements) {
    atsReferenceCache.requirements = fetch('/api/requirements').then(r => r.json());
  }
  return atsReferenceCache.requirements;
}

async function getAtsTeamRows() {
  if (!atsReferenceCache.team) {
    atsReferenceCache.team = fetch('/api/team?active_only=1').then(r => r.json());
  }
  return atsReferenceCache.team;
}

function invalidateAtsReferenceCache(keys=['skills','requirements','team']) {
  keys.forEach(key => { atsReferenceCache[key] = null; });
}

function valueOf(id, fallback = '') {
  const el = document.getElementById(id);
  return el ? el.value : fallback;
}

function setValue(id, value = '') {
  const el = document.getElementById(id);
  if (el) el.value = value || '';
}

function renderRequirementOptions(selectId, rows, placeholder='Select Requirement...') {
  const sel = document.getElementById(selectId);
  if (!sel) return;
  sel.innerHTML = `<option value="">${placeholder}</option>`;
  rows.forEach(r => {
    sel.innerHTML += `<option value="${r.id}">${escapeHtml(r.title || '')} - ${escapeHtml(r.client_name || '')}</option>`;
  });
}

let requirementSearchTimer = null;
let requirementSearchSeq = 0;

function requirementLabel(row) {
  return [row.title || '', row.client_name || ''].filter(Boolean).join(' - ') || 'Requirement #' + row.id;
}

function setRequirementPickerMessage(message) {
  const menu = document.getElementById('acRequirementResults');
  if (!menu) return;
  menu.innerHTML = `<button type="button" disabled>${escapeHtml(message)}</button>`;
  menu.classList.add('active');
}

function hideRequirementPicker() {
  const menu = document.getElementById('acRequirementResults');
  if (menu) menu.classList.remove('active');
}

function showRequirementPickerHelp() {
  const selectedId = valueOf('acRequirement');
  const q = valueOf('acRequirementSearch').trim();
  if (!selectedId && q.length < 2) {
    setRequirementPickerMessage('Type at least 2 letters to search active requirements.');
  }
}

function selectRequirementPicker(row) {
  setValue('acRequirement', row.id);
  setValue('acRequirementSearch', requirementLabel(row));
  const hint = document.getElementById('acRequirementHint');
  if (hint) hint.textContent = `${row.status || 'Active'} requirement selected.`;
  hideRequirementPicker();
}

function renderRequirementPickerResults(rows, query) {
  const menu = document.getElementById('acRequirementResults');
  if (!menu) return;
  if (!rows.length) {
    setRequirementPickerMessage(`No active requirements found for "${query}".`);
    return;
  }
  menu.innerHTML = rows.map((row, index) => `
    <button type="button" data-req-index="${index}">
      <strong>${escapeHtml(row.title || 'Untitled requirement')}</strong>
      <span style="display:block;color:#8b95b5;font-size:11px;margin-top:2px">${escapeHtml(row.client_name || '-')} Â· ${escapeHtml(row.status || 'Active')}</span>
    </button>
  `).join('');
  Array.from(menu.querySelectorAll('button[data-req-index]')).forEach(btn => {
    btn.onclick = () => selectRequirementPicker(rows[Number(btn.dataset.reqIndex)]);
  });
  menu.classList.add('active');
}

function queueRequirementSearch(query) {
  setValue('acRequirement', '');
  const hint = document.getElementById('acRequirementHint');
  if (hint) hint.textContent = 'Select one requirement from the search results.';
  clearTimeout(requirementSearchTimer);
  const q = String(query || '').trim();
  if (q.length < 2) {
    showRequirementPickerHelp();
    return;
  }
  requirementSearchTimer = setTimeout(() => searchRequirementPicker(q), 250);
}

async function searchRequirementPicker(query) {
  const seq = ++requirementSearchSeq;
  setRequirementPickerMessage('Searching requirements...');
  try {
    const params = new URLSearchParams({q: query, limit: '25'});
    const res = await fetch('/api/requirements/search?' + params.toString());
    const rows = await res.json();
    if (seq !== requirementSearchSeq) return;
    if (!res.ok || rows.error) throw new Error(rows.error || 'Unable to search requirements');
    renderRequirementPickerResults(Array.isArray(rows) ? rows : [], query);
  } catch (e) {
    if (seq !== requirementSearchSeq) return;
    setRequirementPickerMessage(e.message || 'Unable to search requirements.');
  }
}

function renderRequirementTitleSuggestions(rows) {
  const currentName = String((currentUser && (currentUser.username || currentUser.recruiter_name)) || '').trim().toLowerCase();
  const scopedRows = currentName
    ? (rows || []).filter(r => String(r.created_by || '').trim().toLowerCase() === currentName)
    : (rows || []);
  window.requirementTitleSuggestions = [...new Set(scopedRows.map(r => String(r.title || '').trim()).filter(Boolean))]
    .sort((a, b) => a.localeCompare(b))
    .slice(0, 250);
  showRequirementTitleSuggestions();
}

function showRequirementTitleSuggestions() {
  const input = document.getElementById('reqTitle');
  const menu = document.getElementById('reqTitleSuggestionMenu');
  if (!input || !menu) return;
  const q = input.value.trim().toLowerCase();
  const source = window.requirementTitleSuggestions || [];
  const matches = source
    .filter(title => !q || title.toLowerCase().includes(q))
    .slice(0, 12);
  if (!matches.length) {
    menu.classList.remove('active');
    menu.innerHTML = '';
    return;
  }
  menu.innerHTML = matches.map(title => `<button type="button" onclick="selectRequirementTitleSuggestion('${escapeHtml(title).replace(/'/g, '&#39;')}')">${escapeHtml(title)}</button>`).join('');
  menu.classList.add('active');
}

function selectRequirementTitleSuggestion(title) {
  setValue('reqTitle', title);
  const menu = document.getElementById('reqTitleSuggestionMenu');
  if (menu) menu.classList.remove('active');
}

function filterRequirementSelect(selectId, query) {
  if ((!allRequirementOptions || !allRequirementOptions.length) && String(query || '').trim()) {
    ensureAtsApplicantPicklists();
  }
  const q = String(query || '').toLowerCase().trim();
  const rows = !q ? allRequirementOptions : allRequirementOptions.filter(r =>
    String(r.title || '').toLowerCase().includes(q) ||
    String(r.client_name || '').toLowerCase().includes(q) ||
    String(r.status || '').toLowerCase().includes(q)
  );
  renderRequirementOptions(selectId, rows);
}

async function loadClients(force=false) {
  const rows = await getClientOptionsCached({force});
  populateRequirementClientSelect(rows);
}

function renderMyClientAccessList() {
  const state = window.myClientAccessState || {clients: []};
  const wrap = document.getElementById('myClientSelectedList');
  const status = document.getElementById('myClientAccessStatus');
  if (!wrap) return;
  if (status) status.textContent = '';
  const items = Array.isArray(state.clients) ? state.clients : [];
  if (!items.length) {
    wrap.innerHTML = '<div class="no-data">No clients selected yet. Add one or more client names, then save.</div>';
    return;
  }
  wrap.innerHTML = items.map((client, idx) => `
    <span class="tag" style="display:inline-flex;align-items:center;gap:6px;padding:6px 10px">
      ${escapeHtml(client.client_name || client.name || '')}
      <button type="button" style="background:none;border:0;color:#fff;cursor:pointer;font-weight:900" onclick="removeMyClientName(${idx})">×</button>
    </span>
  `).join('');
}

async function openMyClientAccessModal() {
  closeTopNavMenus();
  try {
    const [myRes, allRes] = await Promise.all([
      fetch('/api/my/clients'),
      getClientOptionsCached({all:true})
    ]);
    const data = await myRes.json();
    const allClients = Array.isArray(allRes) ? allRes : [];
    const clients = Array.isArray(data.clients) ? data.clients.map(c => ({id: c.id, client_name: c.client_name})) : [];
    window.myClientAccessState = {clients};
    window.myClientAccessAllClients = allClients;
    const input = document.getElementById('myClientNameInput');
    if (input) input.value = '';
    const sel = document.getElementById('myClientSelect');
    if (sel) {
      const mapped = new Set(clients.map(c => String(c.client_name || '').trim().toLowerCase()));
      sel.innerHTML = '<option value="">Select existing client...</option>' + (window.myClientAccessAllClients || []).map(c => {
        const name = c.client_name || '';
        const isMapped = mapped.has(String(name).trim().toLowerCase());
        return `<option value="${escapeHtml(name)}" ${isMapped ? 'disabled' : ''}>${escapeHtml(name)}${isMapped ? ' (already added)' : ''}</option>`;
      }).join('');
    }
    renderMyClientAccessList();
    showModal('myClientAccessModal');
  } catch (e) {
    showToast('Unable to load your client access list', 'error');
  }
}

function syncMyClientNameInput() {
  const sel = document.getElementById('myClientSelect');
  const input = document.getElementById('myClientNameInput');
  if (!sel || !input) return;
  const name = (sel.value || '').trim();
  if (name && !input.value.trim()) input.value = name;
}

function addMySelectedClient() {
  const sel = document.getElementById('myClientSelect');
  const name = (sel && sel.value ? sel.value : '').trim();
  if (!name) {
    showToast('Select an existing client first', 'error');
    return;
  }
  const input = document.getElementById('myClientNameInput');
  if (input && !input.value.trim()) input.value = name;
  addMyClientNames();
  if (sel) sel.value = '';
}

function addMyClientNames() {
  const input = document.getElementById('myClientNameInput');
  const state = window.myClientAccessState || {clients: []};
  const current = Array.isArray(state.clients) ? state.clients : [];
  const raw = (input && input.value ? input.value : '').split(/[\n,]+/).map(s => s.trim()).filter(Boolean);
  if (!raw.length) {
    showToast('Type one or more client names first', 'error');
    return;
  }
  const seen = new Set(current.map(c => String(c.client_name || c.name || '').trim().toLowerCase()));
  raw.forEach(name => {
    const key = name.toLowerCase();
    if (seen.has(key)) return;
    seen.add(key);
    current.push({client_name: name});
  });
  state.clients = current;
  window.myClientAccessState = state;
  if (input) input.value = '';
  renderMyClientAccessList();
}

function removeMyClientName(index) {
  const state = window.myClientAccessState || {clients: []};
  const current = Array.isArray(state.clients) ? state.clients : [];
  current.splice(index, 1);
  state.clients = current;
  window.myClientAccessState = state;
  renderMyClientAccessList();
}

async function refreshMyClientAccess() {
  await openMyClientAccessModal();
}

async function saveMyClientAccess() {
  const state = window.myClientAccessState || {clients: []};
  const current = Array.isArray(state.clients) ? state.clients : [];
  const clientNames = current.map(c => c.client_name || c.name || '').map(s => String(s || '').trim()).filter(Boolean);
  if (!clientNames.length) {
    showToast('Add at least one client before saving', 'error');
    return;
  }
  const status = document.getElementById('myClientAccessStatus');
  if (status) {
    status.style.color = '#aab3c8';
    status.textContent = 'Saving client access...';
  }
  try {
    const res = await fetch('/api/my/clients', {
      method: 'PUT',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({client_names: clientNames})
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok || data.error) throw new Error(data.error || 'Unable to save client access');
    if (status) {
      status.style.color = '#61d394';
      status.textContent = `Saved ${data.count || clientNames.length} client${(data.count || clientNames.length) === 1 ? '' : 's'}.`;
    }
    showToast('Client access updated', 'success');
  } catch (e) {
    if (status) {
      status.style.color = '#ffb3b3';
      status.textContent = e.message || 'Unable to save client access';
    }
    showToast(e.message || 'Unable to save client access', 'error');
  }
}

function renderMyGeminiKeyStatus(data) {
  const target = document.getElementById('myGeminiKeyStatus');
  const input = document.getElementById('myGeminiKeyInput');
  if (input) input.value = '';
  if (!target) return;
  const fallbackAvailable = Boolean(data && data.fallback_available);
  const personal = Boolean(data && data.has_personal_key);
  const updatedAt = data && data.updated_at ? String(data.updated_at).replace('T', ' ').replace('Z', '') : '';
  const keyMask = data && data.key_mask ? data.key_mask : '';
  const source = personal ? 'Personal key' : (fallbackAvailable ? 'Org default key' : 'No Gemini key configured');
  target.innerHTML = `
    <div><strong style="color:#fff">${escapeHtml(source)}</strong></div>
    <div>${personal ? `Saved key: <strong>${escapeHtml(keyMask || 'saved')}</strong>` : 'Using the shared org key if one is configured.'}</div>
    <div>${updatedAt ? `Updated: <strong>${escapeHtml(updatedAt)}</strong>` : ''}</div>
  `;
}

async function openMyGeminiKeyModal() {
  closeTopNavMenus();
  await refreshMyGeminiKey();
  showModal('myGeminiKeyModal');
}

async function refreshMyGeminiKey() {
  const status = document.getElementById('myGeminiKeySaveStatus');
  if (status) status.textContent = 'Loading Gemini key status...';
  try {
    const res = await fetch('/api/my/gemini_key');
    const data = await res.json().catch(() => ({}));
    if (!res.ok || data.error) throw new Error(data.error || 'Unable to load Gemini key status');
    renderMyGeminiKeyStatus(data);
    if (status) {
      status.textContent = data.has_personal_key ? 'Personal key is saved for your account.' : 'No personal key saved yet.';
      status.style.color = '#aab3c8';
    }
  } catch (e) {
    if (status) {
      status.textContent = e.message || 'Unable to load Gemini key status';
      status.style.color = '#ffb3b3';
    }
    showToast(e.message || 'Unable to load Gemini key status', 'error');
  }
}

async function saveMyGeminiKey() {
  const input = document.getElementById('myGeminiKeyInput');
  const status = document.getElementById('myGeminiKeySaveStatus');
  const apiKey = String(input && input.value ? input.value : '').trim();
  if (!apiKey) {
    showToast('Paste a Gemini API key or use Clear Personal Key', 'error');
    return;
  }
  if (status) {
    status.textContent = 'Saving Gemini key...';
    status.style.color = '#aab3c8';
  }
  try {
    const res = await fetch('/api/my/gemini_key', {
      method: 'PUT',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({api_key: apiKey})
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok || data.error) throw new Error(data.error || 'Unable to save Gemini key');
    renderMyGeminiKeyStatus(data);
    if (status) {
      status.textContent = 'Gemini key saved securely.';
      status.style.color = '#61d394';
    }
    showToast('Gemini key saved', 'success');
  } catch (e) {
    if (status) {
      status.textContent = e.message || 'Unable to save Gemini key';
      status.style.color = '#ffb3b3';
    }
    showToast(e.message || 'Unable to save Gemini key', 'error');
  }
}

async function clearMyGeminiKey() {
  const status = document.getElementById('myGeminiKeySaveStatus');
  if (status) {
    status.textContent = 'Clearing personal Gemini key...';
    status.style.color = '#aab3c8';
  }
  try {
    const res = await fetch('/api/my/gemini_key', {
      method: 'PUT',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({clear: true})
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok || data.error) throw new Error(data.error || 'Unable to clear Gemini key');
    renderMyGeminiKeyStatus(data);
    if (status) {
      status.textContent = 'Personal Gemini key cleared. The org default will be used if configured.';
      status.style.color = '#61d394';
    }
    showToast('Personal Gemini key cleared', 'success');
  } catch (e) {
    if (status) {
      status.textContent = e.message || 'Unable to clear Gemini key';
      status.style.color = '#ffb3b3';
    }
    showToast(e.message || 'Unable to clear Gemini key', 'error');
  }
}

function renderMyDailyReportEmailsStatus(data) {
  const target = document.getElementById('myDailyReportEmailsStatus');
  const input = document.getElementById('myDailyReportEmailsInput');
  if (input) input.value = '';
  if (!target) return;
  const emails = Array.isArray(data && data.email_list) ? data.email_list : [];
  const updatedAt = data && data.updated_at ? String(data.updated_at).replace('T', ' ').replace('Z', '') : '';
  target.innerHTML = emails.length
    ? `<div><strong style="color:#fff">${emails.length} saved email${emails.length === 1 ? '' : 's'}</strong></div><div>${escapeHtml(emails.join(', '))}</div>${updatedAt ? `<div>Updated: <strong>${escapeHtml(updatedAt)}</strong></div>` : ''}`
    : '<div><strong style="color:#fff">No saved recipient list yet</strong></div><div>You can keep using manual entry without saving anything here.</div>';
}

function populateDailyReportEmailPresetOptions(emails) {
  const sel = document.getElementById('dailyReportEmailPreset');
  if (!sel) return;
  const current = (document.getElementById('dailyReportEmail')?.value || '').trim().toLowerCase();
  const options = Array.isArray(emails) ? emails : [];
  sel.innerHTML = '<option value="">Select a saved email ID...</option>' + options.map(email => {
    const value = String(email || '').trim();
    const selected = current && current === value.toLowerCase() ? 'selected' : '';
    return `<option value="${escapeHtml(value)}" ${selected}>${escapeHtml(value)}</option>`;
  }).join('');
}

function applyDailyReportRecipientPreset() {
  const sel = document.getElementById('dailyReportEmailPreset');
  const input = document.getElementById('dailyReportEmail');
  if (!sel || !input) return;
  const value = String(sel.value || '').trim();
  if (value) {
    input.value = value;
    localStorage.setItem('hrguru_daily_report_email', value);
  }
}

async function refreshMyDailyReportEmails() {
  const status = document.getElementById('myDailyReportEmailsSaveStatus');
  if (status) status.textContent = 'Loading daily report email list...';
  try {
    const res = await fetch('/api/my/daily_report_emails');
    const data = await res.json().catch(() => ({}));
    if (!res.ok || data.error) throw new Error(data.error || 'Unable to load daily report email list');
    renderMyDailyReportEmailsStatus(data);
    if (status) {
      status.textContent = data.has_saved_list ? 'Saved recipient list loaded.' : 'No saved recipient list yet.';
      status.style.color = '#aab3c8';
    }
  } catch (e) {
    if (status) {
      status.textContent = e.message || 'Unable to load daily report email list';
      status.style.color = '#ffb3b3';
    }
    showToast(e.message || 'Unable to load daily report email list', 'error');
  }
}

async function loadDailyReportEmailPresetOptions() {
  try {
    const res = await fetch('/api/my/daily_report_emails');
    const data = await res.json().catch(() => ({}));
    if (!res.ok || data.error) throw new Error(data.error || 'Unable to load daily report email list');
    populateDailyReportEmailPresetOptions(data.email_list || []);
  } catch (e) {
    populateDailyReportEmailPresetOptions([]);
    console.warn('Unable to load daily report email presets', e);
  }
}

async function openMyDailyReportEmailsModal() {
  closeTopNavMenus();
  await refreshMyDailyReportEmails();
  showModal('myDailyReportEmailsModal');
}

async function saveMyDailyReportEmails() {
  const input = document.getElementById('myDailyReportEmailsInput');
  const status = document.getElementById('myDailyReportEmailsSaveStatus');
  const raw = String(input && input.value ? input.value : '').trim();
  const emails = raw ? raw.split(/[\n,;]+/).map(v => v.trim()).filter(Boolean) : [];
  if (!emails.length) {
    showToast('Paste one or more email IDs or use Clear Saved List', 'error');
    return;
  }
  if (status) {
    status.textContent = 'Saving email list...';
    status.style.color = '#aab3c8';
  }
  try {
    const res = await fetch('/api/my/daily_report_emails', {
      method: 'PUT',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({email_list: emails})
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok || data.error) throw new Error(data.error || 'Unable to save daily report email list');
    renderMyDailyReportEmailsStatus(data);
    if (status) {
      status.textContent = 'Daily report email list saved.';
      status.style.color = '#61d394';
    }
    showToast('Daily report email list saved', 'success');
  } catch (e) {
    if (status) {
      status.textContent = e.message || 'Unable to save daily report email list';
      status.style.color = '#ffb3b3';
    }
    showToast(e.message || 'Unable to save daily report email list', 'error');
  }
}

async function clearMyDailyReportEmails() {
  const status = document.getElementById('myDailyReportEmailsSaveStatus');
  if (status) {
    status.textContent = 'Clearing saved email list...';
    status.style.color = '#aab3c8';
  }
  try {
    const res = await fetch('/api/my/daily_report_emails', {
      method: 'PUT',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({clear: true})
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok || data.error) throw new Error(data.error || 'Unable to clear daily report email list');
    renderMyDailyReportEmailsStatus(data);
    if (status) {
      status.textContent = 'Saved email list cleared.';
      status.style.color = '#61d394';
    }
    showToast('Saved email list cleared', 'success');
  } catch (e) {
    if (status) {
      status.textContent = e.message || 'Unable to clear daily report email list';
      status.style.color = '#ffb3b3';
    }
    showToast(e.message || 'Unable to clear daily report email list', 'error');
  }
}

function formatAiScreeningLogRow(log) {
  const runId = log.run_id || '-';
  const stage = log.stage || '-';
  const status = log.status || '-';
  const candidate = log.candidate_name || `Candidate #${log.candidate_id || '-'}`;
  const requirement = log.requirement_title || `Requirement #${log.requirement_id || '-'}`;
  const time = log.created_at ? String(log.created_at).replace('T', ' ').replace('Z', '') : '-';
  const score = log.score !== null && log.score !== undefined && String(log.score).trim() !== '' ? `${log.score}%` : '-';
  const message = log.message || '';
  return `
    <div class="match-card" style="margin:0;padding:14px">
      <div class="snapshot-grid" style="grid-template-columns:repeat(3,minmax(0,1fr));gap:10px">
        <div><label>Run</label><strong>${escapeHtml(runId)}</strong></div>
        <div><label>Candidate</label><strong>${escapeHtml(candidate)}</strong></div>
        <div><label>Requirement</label><strong>${escapeHtml(requirement)}</strong></div>
        <div><label>Score</label><strong>${escapeHtml(score)}</strong></div>
        <div><label>Stage</label><strong>${escapeHtml(stage)}</strong></div>
        <div><label>Status</label><strong>${escapeHtml(status)}</strong></div>
        <div><label>Time</label><strong>${escapeHtml(time)}</strong></div>
      </div>
      <div style="margin-top:10px;color:#dbe2f1;line-height:1.45">${escapeHtml(message || '-')}</div>
    </div>`;
}

async function loadAiScreeningLogs() {
  const target = document.getElementById('aiScreeningLogsContent');
  if (!target) return;
  target.innerHTML = '<div class="match-card"><p class="muted">Loading AI screening logs...</p></div>';
  try {
    const res = await fetch('/api/ai_screening_logs?limit=10');
    if (!res.ok) throw new Error('Unable to load logs');
    const logs = await res.json();
    if (!Array.isArray(logs) || !logs.length) {
      target.innerHTML = '<div class="match-card"><p class="muted">No screening logs found yet.</p></div>';
      return;
    }
    target.innerHTML = logs.map(formatAiScreeningLogRow).join('');
  } catch (e) {
    target.innerHTML = `<div class="match-card"><p class="muted">${escapeHtml(e.message || 'Unable to load logs')}</p></div>`;
  }
}

async function openAiScreeningLogsModal() {
  closeTopNavMenus();
  await loadAiScreeningLogs();
  showModal('aiScreeningLogsModal');
}

async function triggerCandidateAiScreening(id, btn) {
  if (!id) {
    showToast('Select a candidate first', 'error');
    return;
  }
  const button = btn || null;
  const originalText = button ? button.textContent : '';
  if (button) {
    button.disabled = true;
    button.textContent = 'Running...';
  }
  try {
    const res = await fetch(`/api/candidate/${id}/ai_screening`, {method: 'POST'});
    const data = await res.json().catch(() => ({}));
    if (!res.ok || data.error) throw new Error(data.error || 'Unable to start AI screening');
    showToast(data.message || 'AI screening queued', 'success');
    await loadDashboardCandidateList();
    if (window.currentCandidateId === id) {
      await showCandidateDetail(id);
    }
  } catch (e) {
    showToast(e.message || 'Unable to start AI screening', 'error');
  } finally {
    if (button) {
      button.disabled = false;
      button.textContent = originalText || 'Run';
    }
  }
}

async function runCandidateAiScreening() {
  const candidate = window.currentCandidate || {};
  const id = candidate.id || window.currentCandidateId;
  if (!id) {
    showToast('Select a candidate first', 'error');
    return;
  }
  const btn = document.getElementById('runAiScreeningBtn');
  if (btn) {
    btn.disabled = true;
    btn.textContent = 'Running...';
  }
  try {
    const res = await fetch(`/api/candidate/${id}/ai_screening`, {method: 'POST'});
    const data = await res.json().catch(() => ({}));
    if (!res.ok || data.error) throw new Error(data.error || 'Unable to start AI screening');
    showToast(data.message || 'AI screening queued', 'success');
    await showCandidateDetail(id);
    await loadDashboardCandidateList();
  } catch (e) {
    showToast(e.message || 'Unable to start AI screening', 'error');
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.textContent = 'Run AI Screening';
    }
  }
}

async function openClientMasterModal() {
  closeTopNavMenus();
  const clients = await getClientOptionsCached({force:true, all:true});
  const sel = document.getElementById('setupClientSelect');
  const status = document.getElementById('setupClientMasterStatus');
  if (!sel) return;
  sel.innerHTML = '<option value="">Select Client...</option>';
  clients.forEach(c => {
    sel.innerHTML += `<option value="${c.id}" data-name="${escapeHtml(c.client_name)}">${escapeHtml(c.client_name)}</option>`;
  });
  setValue('setupClientName', '');
  if (status) status.textContent = '';
  showModal('setupClientModal');
}

async function openSetupClientEditor() {
  return openClientMasterModal();
}

function setSetupClientName() {
  const sel = document.getElementById('setupClientSelect');
  const opt = sel?.selectedOptions?.[0];
  setValue('setupClientName', opt ? opt.dataset.name || '' : '');
}

async function refreshClientMasterAfterChange() {
  await loadFilterOptions(true);
  await loadClients(true);
  await loadRequirements();
  await loadDashboardCandidateList();
  await loadCandidateStats();
  await openClientMasterModal();
}

async function saveSetupClient() {
  const id = valueOf('setupClientSelect');
  const clientName = valueOf('setupClientName').trim();
  const status = document.getElementById('setupClientMasterStatus');
  if (!id || !clientName) {
    showToast('Select a client and enter a name', 'error');
    return;
  }
  if (status) {
    status.style.color = '#aab3c8';
    status.textContent = 'Updating client...';
  }
  const res = await fetch('/api/clients/' + id, {
    method: 'PATCH',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({client_name: clientName})
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok || data.error) {
    if (status) {
      status.style.color = '#ffb3b3';
      status.textContent = data.error || 'Unable to update client';
    }
    showToast(data.error || 'Unable to update client', 'error');
    return;
  }
  if (status) {
    status.style.color = '#61d394';
    status.textContent = 'Client updated successfully.';
  }
  await refreshClientMasterAfterChange();
  showToast('Client updated', 'success');
}

async function addSetupClient() {
  const clientName = valueOf('setupClientName').trim();
  const status = document.getElementById('setupClientMasterStatus');
  if (!clientName) {
    showToast('Enter a client name first', 'error');
    return;
  }
  if (status) {
    status.style.color = '#aab3c8';
    status.textContent = 'Adding client...';
  }
  const res = await fetch('/api/clients', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({client_name: clientName})
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok || data.error) {
    if (status) {
      status.style.color = '#ffb3b3';
      status.textContent = data.error || 'Unable to add client';
    }
    showToast(data.error || 'Unable to add client', 'error');
    return;
  }
  if (status) {
    status.style.color = '#61d394';
    status.textContent = data.created ? 'Client added successfully.' : 'Client already existed.';
  }
  await refreshClientMasterAfterChange();
  showToast(data.created ? 'Client added' : 'Client already exists', data.created ? 'success' : 'info');
}

async function deleteSetupClient() {
  const id = valueOf('setupClientSelect');
  const clientName = valueOf('setupClientName').trim();
  const status = document.getElementById('setupClientMasterStatus');
  if (!id) {
    showToast('Select a client to delete', 'error');
    return;
  }
  const ok = await confirmAction({
    title: 'Delete client?',
    message: `Delete ${clientName || 'this client'} from the master list? This cannot be undone.`,
    okText: 'Delete'
  });
  if (!ok) return;
  if (status) {
    status.style.color = '#aab3c8';
    status.textContent = 'Deleting client...';
  }
  const res = await fetch('/api/clients/' + id, {method: 'DELETE'});
  const data = await res.json().catch(() => ({}));
  if (!res.ok || data.error) {
    const usage = data.usage ? ` Requirements: ${data.usage.requirements || 0}, Jobs: ${data.usage.jobs || 0}, Mappings: ${data.usage.team_mappings || 0}.` : '';
    const message = (data.error || 'Unable to delete client') + usage;
    if (status) {
      status.style.color = '#ffb3b3';
      status.textContent = message;
    }
    showToast(message, 'error');
    return;
  }
  setValue('setupClientName', '');
  if (status) {
    status.style.color = '#61d394';
    status.textContent = 'Client deleted successfully.';
  }
  await refreshClientMasterAfterChange();
  showToast('Client deleted', 'success');
}

async function backupAtsToGoogleDrive() {
  if (!currentUser || !currentUser.is_admin) {
    showToast('Admin access required', 'error');
    return;
  }
  const link = document.getElementById('backupGoogleDriveLink');
  const status = document.getElementById('backupGoogleDriveStatus');
  if (link) {
    link.style.pointerEvents = 'none';
    link.style.opacity = '0.65';
  }
  if (status) status.textContent = 'Creating backup and uploading to Google Drive...';
  try {
    const res = await fetch('/api/admin/backup/google-drive', {method: 'POST'});
    const data = await res.json().catch(() => ({}));
    if (!res.ok || !data.ok) {
      throw new Error(data.error || 'Backup failed');
    }
    const linkHtml = data.link ? ` <a href="${escapeHtml(data.link)}" target="_blank" rel="noopener">Open in Drive</a>` : '';
    if (status) status.innerHTML = `Backup completed: ${escapeHtml(data.filename || 'ATS backup')}.${linkHtml}`;
    showToast('ATS backup uploaded to Google Drive', 'success');
  } catch (e) {
    if (status) status.textContent = e.message;
    showToast(e.message, 'error');
  } finally {
    if (link) {
      link.style.pointerEvents = '';
      link.style.opacity = '';
    }
  }
}

async function openSetupRequirementPicker() {
  const rows = await fetch('/api/requirements').then(r => r.json());
  window.setupRequirementOptions = Array.isArray(rows) ? rows : (rows.rows || []);
  setValue('setupRequirementSearch', '');
  renderRequirementOptions('setupRequirementSelect', window.setupRequirementOptions, 'Select Requirement...');
  showModal('setupRequirementModal');
}

function filterSetupRequirementSelect() {
  const q = valueOf('setupRequirementSearch').toLowerCase().trim();
  const rows = !q ? (window.setupRequirementOptions || []) : (window.setupRequirementOptions || []).filter(r =>
    String(r.title || '').toLowerCase().includes(q) ||
    String(r.client_name || '').toLowerCase().includes(q) ||
    String(r.status || '').toLowerCase().includes(q)
  );
  renderRequirementOptions('setupRequirementSelect', rows, 'Select Requirement...');
}

function editSelectedSetupRequirement() {
  const id = valueOf('setupRequirementSelect');
  if (!id) {
    showToast('Select a requirement first', 'error');
    return;
  }
  closeModal('setupRequirementModal');
  editRequirement(id);
}

async function openTeamClientMappingModal() {
  closeTopNavMenus();
  if (!currentUser.is_admin) {
    showToast('Admin access required', 'error');
    return;
  }
  const [team, clients, mappings] = await Promise.all([
    fetch('/api/team?active_only=1').then(r => r.json()),
    getClientOptionsCached(),
    fetch('/api/team-client-mappings').then(r => r.json())
  ]);
  window.teamClientMappingState = {
    team: Array.isArray(team) ? team : [],
    clients: Array.isArray(clients) ? clients : [],
    mappings: mappings || {}
  };
  const sel = document.getElementById('mappingTeamSelect');
  sel.innerHTML = '<option value="">Select Team Member...</option>';
  window.teamClientMappingState.team.forEach(member => {
    sel.innerHTML += `<option value="${member.id}">${escapeHtml(member.name || member.email || 'Team Member')} ${member.email ? '(' + escapeHtml(member.email) + ')' : ''}</option>`;
  });
  document.getElementById('mappingClientChecks').innerHTML = '<div class="no-data">Select a team member to map clients.</div>';
  const cancelBtn = document.getElementById('teamClientMappingCancelBtn');
  if (cancelBtn) cancelBtn.textContent = 'Cancel';
  showModal('teamClientMappingModal');
}

function renderTeamClientChecks() {
  const state = window.teamClientMappingState || {clients: [], mappings: {}};
  const teamId = valueOf('mappingTeamSelect');
  const wrap = document.getElementById('mappingClientChecks');
  const status = document.getElementById('mappingSaveStatus');
  if (status) status.textContent = '';
  if (!teamId) {
    wrap.innerHTML = '<div class="no-data">Select a team member to map clients.</div>';
    return;
  }
  const selected = new Set((state.mappings[String(teamId)] || []).map(c => String(c.id)));
  wrap.innerHTML = state.clients.map(client => `
    <label style="display:flex;gap:8px;align-items:center;padding:8px;border:1px solid #2a2f3a;border-radius:8px;background:#1c2030">
      <input type="checkbox" class="mapping-client-check" value="${client.id}" ${selected.has(String(client.id)) ? 'checked' : ''}>
      <span>${escapeHtml(client.client_name)}</span>
    </label>
  `).join('') || '<div class="no-data">No clients found.</div>';
}

async function saveTeamClientMapping() {
  const btn = document.getElementById('saveTeamClientMappingBtn');
  const status = document.getElementById('mappingSaveStatus');
  if (status) {
    status.style.color = '#aab3c8';
    status.textContent = '';
  }
  const teamId = valueOf('mappingTeamSelect');
  if (!teamId) {
    if (status) status.textContent = 'Select a team member first.';
    showToast('Select a team member first', 'error');
    return;
  }
  const clientIds = Array.from(document.querySelectorAll('.mapping-client-check:checked')).map(cb => Number(cb.value));
  if (!clientIds.length) {
    if (status) status.textContent = 'Select at least one client before saving.';
    showToast('Select at least one client for this team member', 'error');
    return;
  }
  if (btn) {
    btn.disabled = true;
    btn.textContent = 'Saving...';
  }
  if (status) status.textContent = 'Saving mapping...';
  try {
    const res = await fetch(`/api/team/${teamId}/clients`, {
      method: 'PUT',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({client_ids: clientIds})
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok || data.error) throw new Error(data.error || 'Unable to save mapping');
    window.teamClientMappingState.mappings[String(teamId)] = clientIds.map(id => {
      const client = window.teamClientMappingState.clients.find(c => Number(c.id) === id);
      return {id, client_name: client ? client.client_name : ''};
    });
    if (status) {
      status.style.color = '#61d394';
      status.textContent = `Saved ${clientIds.length} client${clientIds.length === 1 ? '' : 's'} for this team member.`;
    }
    const cancelBtn = document.getElementById('teamClientMappingCancelBtn');
    if (cancelBtn) cancelBtn.textContent = 'Close';
    showToast('Client mapping saved', 'success');
  } catch(e) {
    if (status) {
      status.style.color = '#ff8a8a';
      status.textContent = e.message || 'Unable to save mapping.';
    }
    showToast(e.message || 'Unable to save mapping', 'error');
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.textContent = 'Save Mapping';
    }
  }
}

function handleClientSelect() {
  const sel = document.getElementById('reqClientSel');
  if (!sel) return;
}

async function loadStats() {
  return loadCandidateStats();
}

async function loadFilterOptions() {
  try {
    const [requirementsPayload, statuses, clientsPayload, searchFilters] = await Promise.all([
      fetch('/api/requirements').then(r => r.json()),
      fetch('/api/statuses').then(r => r.json()),
      fetch('/api/clients').then(r => r.json()).catch(() => []),
      fetch('/api/candidate_search_filters').then(r => r.json()).catch(() => ({clients: [], sourcers: []}))
    ]);
    const requirements = Array.isArray(requirementsPayload) ? requirementsPayload : (requirementsPayload.rows || []);
    const mappedClients = Array.isArray(clientsPayload) ? clientsPayload : [];
    cacheClientOptions(mappedClients);
    const requirementClients = requirements.map(r => r.client_name).filter(Boolean);
    const clientNames = [...new Set([
      ...((searchFilters && searchFilters.clients) || []).filter(Boolean),
      ...mappedClients.map(c => c.client_name).filter(Boolean),
      ...requirementClients
    ])].sort((a, b) => a.localeCompare(b));
    const clientSel = document.getElementById('clientFilter');
    if (clientSel) {
      clientSel.innerHTML = '<option value="">All Clients</option>';
      clientNames.forEach(client => { clientSel.innerHTML += '<option value="'+escapeHtml(client)+'">'+escapeHtml(client)+'</option>'; });
    }
    const searchClientSel = document.getElementById('candidateSearchClient');
    if (searchClientSel) {
      const selectedClient = searchClientSel.value;
      searchClientSel.innerHTML = '<option value="">All Clients</option>';
      clientNames.forEach(client => { searchClientSel.innerHTML += '<option value="'+escapeHtml(client)+'">'+escapeHtml(client)+'</option>'; });
      if (selectedClient && clientNames.includes(selectedClient)) searchClientSel.value = selectedClient;
    }
    const reportingClientSel = document.getElementById('reportingClientFilter');
    if (reportingClientSel) {
      const selectedClient = reportingClientSel.value;
      reportingClientSel.innerHTML = '<option value="">All Clients</option>';
      clientNames.forEach(client => { reportingClientSel.innerHTML += '<option value="'+escapeHtml(client)+'">'+escapeHtml(client)+'</option>'; });
      if (selectedClient && clientNames.includes(selectedClient)) reportingClientSel.value = selectedClient;
    }
    const analyticsClientSel = document.getElementById('analyticsClientFilter');
    if (analyticsClientSel) {
      const selectedClient = analyticsClientSel.value;
      analyticsClientSel.innerHTML = '<option value="">All Clients</option>';
      clientNames.forEach(client => { analyticsClientSel.innerHTML += '<option value="'+escapeHtml(client)+'">'+escapeHtml(client)+'</option>'; });
      if (selectedClient && clientNames.includes(selectedClient)) analyticsClientSel.value = selectedClient;
    }
    const reqSel = document.getElementById('reqFilter');
    if (reqSel && requirements.length > 0) {
      allRequirementOptions = requirements;
      reqSel.innerHTML = '<option value="">All Requirements</option>';
      requirements.forEach(r => { reqSel.innerHTML += '<option value="'+r.id+'">'+escapeHtml(r.title)+' - '+escapeHtml(r.client_name||'')+'</option>'; });
    }
    populateRequirementClientSelect(mappedClients);
    const recruiterSel = document.getElementById('recruiterFilter');
    if (recruiterSel) {
      recruiterSel.style.display = currentUser && currentUser.is_admin ? '' : 'none';
      recruiterSel.innerHTML = '<option value="">All Recruiters</option>';
      if (currentUser && currentUser.is_admin) {
        const recruiters = [...new Map((await fetch('/api/team?active_only=1').then(r => r.json())).map(r => [r.email || r.name, r])).values()];
        recruiters.forEach(r => { if (r.email) recruiterSel.innerHTML += '<option value="'+r.email+'">'+r.name+'</option>'; });
      }
    }
    const searchSourcerSel = document.getElementById('candidateSearchSourcer');
    if (searchSourcerSel) {
      searchSourcerSel.innerHTML = '<option value="">All Sourcers</option>';
      const filterSourcers = Array.isArray(searchFilters && searchFilters.sourcers) ? searchFilters.sourcers : [];
      const team = currentUser && currentUser.is_admin ? await fetch('/api/team?active_only=1').then(r => r.json()) : [];
      const sourcers = [...new Map([
        ...filterSourcers.filter(r => r.email).map(r => [String(r.email).toLowerCase(), r]),
        ...(Array.isArray(team) ? team : []).filter(r => r.email).map(r => [String(r.email).toLowerCase(), r])
      ]).values()];
      sourcers.forEach(r => { searchSourcerSel.innerHTML += '<option value="'+String(r.email).toLowerCase()+'">'+escapeHtml(r.name || r.email)+'</option>'; });
    }
    const statSel = document.getElementById('statusFilter');
    if (statSel) {
      statSel.innerHTML = '<option value="">All Statuses</option>';
      CANDIDATE_STATUSES.forEach(s => { statSel.innerHTML += '<option value="'+s+'">'+s+'</option>'; });
    }
  } catch(e) {
    console.error('Failed to load filter options', e);
  }
}


async function loadCandidateStats() {
  try {
    const res = await fetch('/api/stats?' + buildCandidateFilterParams(false));
    const data = await res.json();
    const setStat = (ids, value) => ids.forEach(id => {
      const el = document.getElementById(id);
      if (el) el.textContent = value || 0;
    });
    const counts = data.status_counts || {};
    setStat(['candTotal', 'dashCandTotal'], data.total);
    setStat(['candDuplicates', 'dashCandDuplicates'], data.duplicates);
    setStat(['candNew', 'dashCandNew'], counts['New']);
    setStat(['candShortlisted', 'dashCandShortlisted'], counts['Shortlisted']);
    setStat(['candScreening', 'dashCandScreening'], counts['Screening Pending']);
    setStat(['candInterviewed', 'dashCandInterviewed'], counts['Interviewed']);
    setStat(['candOffered', 'dashCandOffered'], counts['Offered']);
    setStat(['candJoined', 'dashCandJoined'], counts['Joined']);
  } catch(e) {
    console.error('Error loading candidate stats:', e);
  }
}

function renderSummaryTrend(rows) {
  renderSummaryTrendFor('summaryTrendGraph', rows, 'No submissions in the last 14 days.');
}

function renderSummaryTrendFor(targetId, rows, emptyText) {
  const target = document.getElementById(targetId);
  if (!target) return;
  const safeRows = Array.isArray(rows) ? rows : [];
  const maxCount = Math.max(1, ...safeRows.map(row => Number(row.count || 0)));
  if (!safeRows.length || safeRows.every(row => Number(row.count || 0) === 0)) {
    target.innerHTML = `<div class="graph-empty">${escapeHtml(emptyText || 'No data available.')}</div>`;
    return;
  }
  target.innerHTML = safeRows.map(row => {
    const count = Number(row.count || 0);
    const height = Math.max(4, Math.round((count / maxCount) * 145));
    return `
      <div class="bar-item" title="${escapeHtml(row.label || row.date || '')}: ${count}">
        <div class="bar-count">${count ? count.toLocaleString('en-IN') : ''}</div>
        <div class="bar-fill" style="--h:${height}px"></div>
        <div class="bar-label">${escapeHtml(row.label || '')}</div>
      </div>
    `;
  }).join('');
}

function renderSummaryBarList(targetId, rows, emptyText) {
  const target = document.getElementById(targetId);
  if (!target) return;
  const safeRows = Array.isArray(rows) ? rows : [];
  const maxCount = Math.max(1, ...safeRows.map(row => Number(row.count || 0)));
  if (!safeRows.length || safeRows.every(row => Number(row.count || 0) === 0)) {
    target.innerHTML = `<div class="graph-empty">${escapeHtml(emptyText)}</div>`;
    return;
  }
  target.innerHTML = safeRows.map(row => {
    const count = Number(row.count || 0);
    const width = Math.max(4, Math.round((count / maxCount) * 100));
    const label = row.label || '-';
    return `
      <div class="hbar-row" title="${escapeHtml(label)}: ${count}">
        <div class="hbar-label">${escapeHtml(label)}</div>
        <div class="hbar-count">${count.toLocaleString('en-IN')}</div>
        <div class="hbar-track"><div class="hbar-fill" style="--w:${width}%"></div></div>
      </div>
    `;
  }).join('');
}

function renderDashboardNoSubmissionTodayList(rows, emptyText) {
  const target = document.getElementById('summaryNoSubmissionTodayList');
  const countEl = document.getElementById('summaryNoSubmissionTodayCount');
  const panel = document.getElementById('summaryNoSubmissionTodayPanel');
  const link = document.getElementById('summaryNoSubmissionTodayLink');
  if (!target) return;
  const safeRows = Array.isArray(rows) ? rows : [];
  if (countEl) countEl.textContent = String(safeRows.length || 0);
  if (panel) panel.classList.toggle('active', summaryNoSubmissionTodayExpanded);
  if (link) link.innerHTML = summaryNoSubmissionTodayExpanded ? 'Click to hide list &#8250;' : 'Click to view list &#8250;';
  if (!safeRows.length) {
    target.innerHTML = `<div class="graph-empty">${escapeHtml(emptyText)}</div>`;
    return;
  }
  target.innerHTML = safeRows.map(row => `
    <div class="dashboard-person-row" title="${escapeHtml(row.name || '')} ${row.email ? ' - ' + row.email : ''}">
      <div>
        <span class="dashboard-person-name">${escapeHtml(row.name || 'Unassigned')}</span>
        <span class="dashboard-person-email">${escapeHtml(row.email || '')}</span>
      </div>
      <span class="dashboard-person-badge">Pending</span>
    </div>
  `).join('');
}

function toggleNoSubmissionTodayList() {
  summaryNoSubmissionTodayExpanded = !summaryNoSubmissionTodayExpanded;
  const panel = document.getElementById('summaryNoSubmissionTodayPanel');
  const link = document.getElementById('summaryNoSubmissionTodayLink');
  if (panel) panel.classList.toggle('active', summaryNoSubmissionTodayExpanded);
  if (link) link.innerHTML = summaryNoSubmissionTodayExpanded ? 'Click to hide list &#8250;' : 'Click to view list &#8250;';
}

function exportNoSubmissionTodayFromDashboard() {
  const summary = window.currentDashboardSummary || {};
  const rows = Array.isArray(summary.no_submission_today) ? summary.no_submission_today : [];
  if (!rows.length) {
    showToast('No recruiter list available to export.', 'error');
    return;
  }
  const stamp = new Date().toISOString().slice(0, 10);
  const csvRows = [['Recruiters Pending Submission'], ['Name', 'Email']];
  rows.forEach(r => csvRows.push([r.name || '-', r.email || '-']));
  downloadCsv(`dashboard_no_submission_today_${stamp}.csv`, csvRows);
}

function scheduleFullDashboardSummaryLoad() {
  if (dashboardSummaryFullLoaded || dashboardSummaryIdleScheduled) return;
  dashboardSummaryIdleScheduled = true;
  const run = () => {
    dashboardSummaryIdleScheduled = false;
    loadRecruiterDashboardSummary({light:false});
  };
  if ('requestIdleCallback' in window) {
    window.requestIdleCallback(run, {timeout: 2500});
  } else {
    setTimeout(run, 900);
  }
}

async function loadRecruiterDashboardSummary({light=false, deferFull=false} = {}) {
  const summary = document.getElementById('recruiterDashboardSummary');
  if (!summary) return;
  try {
    const params = new URLSearchParams({
      recruiter_view: summaryRecruiterView || 'month',
      client_view: summaryClientView || 'month'
    });
    if (light) params.set('light', '1');
    const res = await fetch('/api/dashboard_summary?' + params.toString());
    const data = await res.json();
    if (!res.ok || data.error) throw new Error(data.error || 'Unable to load dashboard summary');
    window.currentDashboardSummary = data;
    const isAdmin = Boolean(currentUser && currentUser.is_admin);
    const setText = (id, value) => {
      const el = document.getElementById(id);
      if (el) el.textContent = Number(value || 0).toLocaleString('en-IN');
    };
    const graphTitle = document.getElementById('summarySecondaryGraphTitle');
    const graphLabel = document.getElementById('summarySecondaryGraphLabel');
    const graphToggle = document.getElementById('summarySecondaryGraphToggle');
    const pendingShell = document.getElementById('summaryNoSubmissionTodayShell');
    if (graphToggle) graphToggle.style.display = isAdmin ? 'flex' : 'none';
    if (pendingShell) pendingShell.style.display = isAdmin ? 'block' : 'none';
    setText('sumDailySubmissions', data.daily_submissions);
    setText('sumWeeklySubmissions', data.weekly_submissions);
    setText('sumMonthlySubmissions', data.monthly_submissions);
    setText('sumMonthlySelections', data.monthly_selections);
    setText('sumMonthlyRequirements', data.monthly_requirements_worked);
    if (data.light) {
      if (deferFull) scheduleFullDashboardSummaryLoad();
      return;
    }
    dashboardSummaryFullLoaded = true;
    renderSummaryTrend(data.daily_trend || []);
    renderSummaryTrendFor('summarySelectionTrendGraph', data.selection_trend || [], 'No selections in the last 14 days.');
    if (isAdmin) {
      if (graphTitle) graphTitle.textContent = 'Recruiter Submissions';
      if (graphLabel) graphLabel.textContent = (data.recruiter_view === 'today') ? 'Today' : 'Current month';
      if (graphToggle) {
        const monthBtn = document.getElementById('summaryRecruiterMonthBtn');
        const todayBtn = document.getElementById('summaryRecruiterTodayBtn');
        if (monthBtn) monthBtn.classList.toggle('active', (data.recruiter_view || 'month') === 'month');
        if (todayBtn) todayBtn.classList.toggle('active', (data.recruiter_view || 'month') === 'today');
      }
      renderSummaryBarList('summaryStatusGraph', data.recruiter_breakdown || [], (data.recruiter_view === 'today') ? 'No recruiter submissions today.' : 'No recruiter submissions this month.');
      const empty = document.getElementById('summarySecondaryGraphEmpty');
      if (empty) empty.textContent = (data.recruiter_view === 'today') ? 'Loading today\'s recruiter submissions...' : 'Loading recruiter submissions...';
    } else {
      if (graphTitle) graphTitle.textContent = 'Status Mix';
      if (graphLabel) graphLabel.textContent = 'Current month';
      renderSummaryBarList('summaryStatusGraph', data.status_breakdown || [], 'No candidate status activity this month.');
      const empty = document.getElementById('summarySecondaryGraphEmpty');
      if (empty) empty.textContent = 'Loading status...';
    }
    const clientTitle = document.getElementById('summaryClientGraphTitle');
    const clientLabel = document.getElementById('summaryClientGraphLabel');
    const clientMonthBtn = document.getElementById('summaryClientMonthBtn');
    const clientTodayBtn = document.getElementById('summaryClientTodayBtn');
    const clientToggle = document.getElementById('summaryClientGraphToggle');
    if (clientToggle) clientToggle.style.display = 'flex';
    if (clientTitle) clientTitle.textContent = 'Client-wise Submissions';
    if (clientLabel) clientLabel.textContent = (data.client_view === 'today') ? 'Today' : 'Current month';
    if (clientMonthBtn) clientMonthBtn.classList.toggle('active', (data.client_view || 'month') === 'month');
    if (clientTodayBtn) clientTodayBtn.classList.toggle('active', (data.client_view || 'month') === 'today');
    renderSummaryBarList('summaryClientGraph', data.client_breakdown || [], (data.client_view === 'today') ? 'No client submissions today.' : 'No client submissions this month.');
    const clientEmpty = document.getElementById('summaryClientGraphEmpty');
    if (clientEmpty) clientEmpty.textContent = (data.client_view === 'today') ? 'Loading today\'s client submissions...' : 'Loading client submissions...';
    renderDashboardNoSubmissionTodayList(data.no_submission_today || [], 'All recruiters have submitted today.');
  } catch(e) {
    console.error('Error loading dashboard summary:', e);
    renderSummaryTrend([]);
    const isAdmin = Boolean(currentUser && currentUser.is_admin);
    renderSummaryBarList('summaryStatusGraph', [], isAdmin ? 'Unable to load recruiter submissions.' : 'Unable to load status activity.');
    renderSummaryBarList('summaryClientGraph', [], 'Unable to load client submissions.');
    renderDashboardNoSubmissionTodayList([], 'Unable to load recruiter submission status.');
  }
}

function setSummaryRecruiterView(view) {
  const normalized = view === 'today' ? 'today' : 'month';
  if (summaryRecruiterView === normalized) return;
  summaryRecruiterView = normalized;
  const monthBtn = document.getElementById('summaryRecruiterMonthBtn');
  const todayBtn = document.getElementById('summaryRecruiterTodayBtn');
  if (monthBtn) monthBtn.classList.toggle('active', normalized === 'month');
  if (todayBtn) todayBtn.classList.toggle('active', normalized === 'today');
  dashboardSummaryFullLoaded = false;
  loadRecruiterDashboardSummary({light:false});
}

function setSummaryClientView(view) {
  const normalized = view === 'today' ? 'today' : 'month';
  if (summaryClientView === normalized) return;
  summaryClientView = normalized;
  const monthBtn = document.getElementById('summaryClientMonthBtn');
  const todayBtn = document.getElementById('summaryClientTodayBtn');
  if (monthBtn) monthBtn.classList.toggle('active', normalized === 'month');
  if (todayBtn) todayBtn.classList.toggle('active', normalized === 'today');
  dashboardSummaryFullLoaded = false;
  loadRecruiterDashboardSummary({light:false});
}

function toggleColumnPanel() {
  const panel = document.getElementById('columnPanel');
  if (panel) panel.classList.toggle('active');
}

function renderColumnPanel() {
  const panel = document.getElementById('columnPanel');
  if (!panel) return;
  panel.innerHTML = candidateColumns.map(col => `
    <label>
      <input type="checkbox" ${visibleCandidateColumns[col.key] ? 'checked' : ''} ${col.required ? 'disabled' : ''} onchange="setCandidateColumn('${col.key}', this.checked)">
      <span>${col.label}</span>
    </label>
  `).join('');
}

function setCandidateColumn(key, visible) {
  visibleCandidateColumns[key] = visible;
  localStorage.setItem('hrguru_candidate_columns', JSON.stringify(visibleCandidateColumns));
  loadCandidates();
}

function colClass(key) {
  return 'col-' + key + (visibleCandidateColumns[key] ? '' : ' col-hidden');
}

function sortHeader(label, key) {
  const sortEl = document.getElementById('sortFilter');
  const current = sortEl ? sortEl.value : (window.currentCandidateSort || 'newest');
  const asc = key + '_asc';
  const desc = key + '_desc';
  const legacyAsc = {name:'name', status:'status', created:'oldest'}[key];
  const legacyDesc = {created:'newest'}[key];
  const isAsc = current === asc || current === legacyAsc;
  const isDesc = current === desc || current === legacyDesc;
  const next = isAsc ? desc : asc;
  const marker = isAsc ? '<span class="sort-indicator">â–²</span>' : (isDesc ? '<span class="sort-indicator">â–¼</span>' : '');
  return `<button type="button" class="sort-th-btn" onclick="setCandidateSort('${next}')">${label}${marker}</button>`;
}

function setCandidateSort(sortValue) {
  window.currentCandidateSort = sortValue;
  loadCandidatesFirstPage();
}

function renderActiveFilterChips() {
  const chips = [];
  const fields = [
    ['searchInput', 'Search'],
    ['clientFilter', 'Client'],
    ['reqFilter', 'Requirement'],
    ['statusFilter', 'Status'],
    ['skillsFilter', 'Skills'],
    ['expFilter', 'Experience'],
    ['datePresetFilter', 'Date'],
    ['recruiterFilter', 'Recruiter']
  ];
  fields.forEach(([id, label]) => {
    const el = document.getElementById(id);
    if (!el || !el.value) return;
    const text = el.tagName === 'SELECT' ? el.options[el.selectedIndex].text : el.value;
    chips.push(`<span class="filter-chip">${label}: ${text}<button type="button" onclick="clearCandidateFilter('${id}')">x</button></span>`);
  });
  const wrap = document.getElementById('activeFilterChips');
  if (wrap) wrap.innerHTML = chips.join('');
}

function clearCandidateFilter(id) {
  const el = document.getElementById(id);
  if (el) el.value = '';
  loadCandidatesFirstPage();
}

function clearCandidateFilters() {
  ['searchInput','clientFilter','reqFilter','statusFilter','skillsFilter','expFilter','datePresetFilter','recruiterFilter'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.value = '';
  });
  loadCandidatesFirstPage();
}


function buildCandidateFilterParams(includeCacheBust = false) {
  const params = new URLSearchParams();
  if (includeCacheBust) params.set('_t', Date.now());
  const fieldValue = id => document.getElementById(id)?.value || '';
  const q = fieldValue('searchInput');
  const client = fieldValue('clientFilter');
  const reqId = fieldValue('reqFilter');
  const statusEl = document.getElementById('statusFilter');
  const status = statusEl ? statusEl.value : '';
    const skills = fieldValue('skillsFilter');
    const expRange = fieldValue('expFilter');
  const datePreset = fieldValue('datePresetFilter');
  const recruiter = fieldValue('recruiterFilter');
    const sortEl = document.getElementById('sortFilter');
    const sort = sortEl ? sortEl.value : (window.currentCandidateSort || 'newest');
  if (q) params.set('q', q);
  if (client) params.set('client', client);
  if (reqId) params.set('requirement_id', reqId);
  if (status) params.set('status', status);
    if (skills) params.set('skills', skills);
    if (expRange) params.set('exp_range', expRange);
  if (datePreset) params.set('date_preset', datePreset);
  if (recruiter && currentUser && currentUser.is_admin) params.set('sender', recruiter);
    if (sort) params.set('sort', sort);
  return params;
}

async function loadCandidates() {
  await loadDashboardCandidateList();
}

function getViewMode() {
  return localStorage.getItem('hrguru_view_mode') || 'table';
}

function initViewMode() {
  const mode = getViewMode();
  const select = document.getElementById('viewMode');
  if (select) select.value = mode;
}

function renderCandidatesEmptyState(message) {
  const mode = getViewMode();
  const grid = document.getElementById('candidatesGrid');
  const table = document.getElementById('candidatesTable');
  const tableWrap = document.getElementById('candidatesTableWrap');
  if (mode === 'table') {
    grid.style.display = 'none';
    tableWrap.style.display = 'block';
    table.style.display = 'table';
    table.innerHTML = '<tbody><tr><td style="text-align:center;padding:40px;color:#6b7494">' + message + '</td></tr></tbody>';
  } else {
    tableWrap.style.display = 'none';
    table.style.display = 'none';
    grid.style.display = 'grid';
    grid.innerHTML = '<div class="no-data">' + message + '</div>';
  }
}

function updateBulkBtn() {
  const checkedCards = document.querySelectorAll('.card-checkbox:checked').length;
  const checkedRows = document.querySelectorAll('.row-checkbox:checked').length;
  const checked = checkedCards + checkedRows;
  const btn = document.getElementById('bulkDeleteBtn');
  if (checked > 0) {
    btn.disabled = false;
    btn.style.opacity = '1';
    btn.textContent = 'Delete (' + checked + ')';
  } else {
    btn.disabled = true;
    btn.style.opacity = '0.5';
    btn.textContent = 'Bulk Delete';
  }
}

async function deleteCandidate(id) {
  const ok = await confirmAction({
    title: 'Delete candidate?',
    message: 'This will remove the candidate from the active list.',
    okText: 'Delete'
  });
  if (!ok) return;
  const res = await fetch('/api/candidate/' + id, {method: 'DELETE'});
  if (res.ok) {
    await loadCandidates();
    loadStats();
    showToast('Candidate deleted', 'success');
  } else {
    showToast('Unable to delete candidate', 'error');
  }
}

function showCandidateDetail(id) {
  window.currentCandidateId = id;
  const cached = getCachedDashboardCandidate(id);
  if (cached) {
    renderCandidateDetail(cached);
    return;
  }
  fetch('/api/candidate/' + id)
    .then(r => {
      if (!r.ok) {
        if (r.status === 403) { showToast('You do not have permission to view this candidate.', 'error'); return null; }
        throw new Error('Failed to load');
      }
      return r.json();
    })
    .then(c => {
      if (!c) return;
      renderCandidateDetail(c);
  })
    .catch(e => {
      console.error('Error loading candidate:', e);
      showToast('Error loading candidate details', 'error');
    });
}

function editCandidateFromDetail() {
  const skillSel = document.getElementById('editCandSkillsSel');
  const candidate = window.currentCandidate || {};
  const currentSkills = (candidate.key_skills || '').split(',').map(s => s.trim()).filter(Boolean);
  getAtsSkills().then(skills => {
    skillSel.innerHTML = '<option value="">Select Skills...</option>';
    let currentCat = '';
    skills.forEach(s => {
      if (s.category !== currentCat) {
        if (currentCat) skillSel.innerHTML += '</optgroup>';
        skillSel.innerHTML += '<optgroup label="'+s.category+'">';
        currentCat = s.category;
      }
      const selected = currentSkills.includes(s.skill_name) ? ' selected' : '';
      skillSel.innerHTML += '<option value="'+s.skill_name+'"'+selected+'>'+s.skill_name+'</option>';
    });
  });
  setValue('editCandRoleTxt', candidate.current_role || '');
  loadRecruiters('editCandRecruiter', candidate.sourcer_id || '').then(() => {
    const recruiterSel = document.getElementById('editCandRecruiter');
    if (recruiterSel) recruiterSel.disabled = !(currentUser && currentUser.is_admin);
  });
  document.getElementById('candidateDetailContent').style.display = 'none';
  document.getElementById('candidateEditForm').style.display = 'block';
  document.getElementById('cdActions').style.display = 'none';
  document.getElementById('editActions').style.display = 'flex';
}

function cancelEditCandidate() {
  document.getElementById('candidateDetailContent').style.display = 'block';
  document.getElementById('candidateEditForm').style.display = 'none';
  document.getElementById('cdActions').style.display = 'flex';
  document.getElementById('editActions').style.display = 'none';
}

async function saveCandidateEdit() {
  document.querySelectorAll('#candidateEditForm .form-group.invalid').forEach(group => group.classList.remove('invalid'));
  document.querySelectorAll('#candidateEditForm .field-error').forEach(err => err.remove());
  const roleTxt = document.getElementById('editCandRoleTxt')?.value || '';
  let currentRole = roleTxt;
  const candidateName = valueOf('editCandName').trim();
  if (!candidateName) {
    markCandidateFieldInvalid('editCandName', 'Candidate name is required');
    document.getElementById('editCandName').scrollIntoView({behavior:'smooth', block:'center'});
    return;
  }
  
  const body = {
    candidate_name: candidateName,
    email_addr: valueOf('editCandEmail').trim(),
    phone: valueOf('editCandPhone').trim(),
    current_company: valueOf('editCandCompany').trim(),
    current_role: currentRole,
    experience_years: valueOf('editCandExp').trim(),
    key_skills: valueOf('editCandSkillsText', valueOf('editCandSkills')).trim(),
    current_location: valueOf('editCandLocation').trim(),
    current_salary: valueOf('editCandCurrSal').trim(),
    expected_salary: valueOf('editCandExpSal').trim(),
    notice_period: valueOf('editCandNotice').trim(),
    remarks: valueOf('editCandRemarks').trim(),
    status: valueOf('editCandStatus', 'New')
  };
  const previousStatus = (window.currentCandidate && window.currentCandidate.status) || 'New';
  if (body.status !== previousStatus) {
    const feedback = window.prompt(`Enter feedback comments for status change to "${body.status}"`);
    if (!feedback || !feedback.trim()) {
      showToast('Feedback comments are required when candidate status changes.', 'error');
      return;
    }
    body.candidate_feedback = feedback.trim();
  }
  const sourcerId = valueOf('editCandRecruiter');
  if (sourcerId) body.sourcer_id = parseInt(sourcerId, 10);

  const id = window.currentCandidateId;
  if (!id) {
    showToast('Candidate ID missing', 'error');
    return;
  }
  const cvFile = document.getElementById('editCandCvFile')?.files?.[0];
  if (cvFile) {
    const status = document.getElementById('editCandCvStatus');
    if (status) status.textContent = 'Uploading CV...';
    const fd = new FormData();
    fd.append('file', cvFile);
    const uploadRes = await fetch('/api/candidate/' + id + '/upload_cv', {method: 'POST', body: fd});
    const uploadData = await uploadRes.json().catch(() => ({}));
    if (!uploadRes.ok || uploadData.error) {
      showToast(uploadData.error || 'Failed to upload CV', 'error');
      if (status) status.textContent = 'CV upload failed.';
      return;
    }
    if (status) status.textContent = 'CV uploaded successfully.';
  }

  const res = await fetch('/api/candidate/' + id, {
  method: 'PATCH',
  headers: {'Content-Type': 'application/json'},
  body: JSON.stringify(body)
  });

  if (!res.ok) {
    const txt = await res.text();
    console.error(txt);
    showToast('Failed to save candidate', 'error');
    return;
  }

  const data = await res.json();

  if (data.ok) {
    closeModal('candidateDetailModal');
    loadDashboardCandidateList();
    loadCandidateStats();
  }

}



async function exportData(fmt, selectedIdsOverride = null) {
  const uniqueIds = Array.isArray(selectedIdsOverride) ? [...new Set(selectedIdsOverride.filter(Boolean))] : getSelectedCandidateIds();
  const params = buildCandidateFilterParams(false);
  params.set('format', fmt);
  if (uniqueIds.length > 0) {
    params.set('ids', uniqueIds.join(','));
  }
  window.location.href = '/api/candidates/export?' + params.toString();
}

function getSelectedCandidateIds() {
  const selectedIds = [];
  document.querySelectorAll('.card-checkbox:checked').forEach(cb => {
    selectedIds.push(cb.closest('.candidate-card')?.dataset?.id);
  });
  document.querySelectorAll('.row-checkbox:checked').forEach(cb => {
    selectedIds.push(cb.dataset?.id);
  });
  document.querySelectorAll('#dashboardCandidateList .dashboard-row-check:checked').forEach(cb => {
    selectedIds.push(cb.value || cb.dataset?.id);
  });
  document.querySelectorAll('.reporting-checkbox:checked').forEach(cb => {
    selectedIds.push(cb.dataset?.id);
  });
  return [...new Set(selectedIds.filter(Boolean))];
}

function dashboardSelectedCandidateIds() {
  return [...document.querySelectorAll('#dashboardCandidateList .dashboard-row-check:checked')]
    .map(cb => cb.value || cb.dataset?.id)
    .filter(Boolean);
}

function exportSelectedCandidates() {
  const selectedIds = dashboardSelectedCandidateIds();
  if (!selectedIds.length) {
    showToast('Select at least one candidate to export.', 'error');
    return;
  }
  exportData('xlsx', selectedIds);
}

let reportingDateFrom = '';
let reportingDateTo = '';
let reportingDatePreset = '';
let reportingRecruitersLoaded = false;
let reportingRows = [];
let reportingRowsCache = {};
let reportingViewState = {sortBy: 'date', sortDir: 'desc', filters: {}, filterDrafts: [['name', '']]};
window.dailyReportSubmitting = false;
window.dailyReportLastSubmittedKey = '';

function hideReportingDateFilters() {
  const fromWrap = document.getElementById('reportingDateFromFilter')?.closest('.reporting-date-filter');
  const toWrap = document.getElementById('reportingDateToFilter')?.closest('.reporting-date-filter');
  if (fromWrap) fromWrap.style.display = 'none';
  if (toWrap) toWrap.style.display = 'none';
}

function splitEmailList(value) {
  return String(value || '')
    .split(/[,\n;]+/)
    .map(item => item.trim().toLowerCase())
    .filter(Boolean)
    .filter((email, index, arr) => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email) && arr.indexOf(email) === index);
}

function validateEmailList(value) {
  const raw = String(value || '').trim();
  if (!raw) return [];
  const emails = splitEmailList(raw);
  const parts = raw.split(/[,\n;]+/).map(item => item.trim()).filter(Boolean);
  if (emails.length !== parts.length) return null;
  return emails;
}

function isoDateLocal(date) {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, '0');
  const d = String(date.getDate()).padStart(2, '0');
  return `${y}-${m}-${d}`;
}

function addDaysIso(isoDate, days) {
  const d = new Date(`${isoDate}T00:00:00`);
  d.setDate(d.getDate() + days);
  return isoDateLocal(d);
}

function reportingFilterParams() {
  const today = isoDateLocal(new Date());
  const preset = reportingDatePreset || '';
  let dateFrom = reportingDateFrom || '';
  let dateTo = reportingDateTo || '';
  if (!dateFrom && !dateTo && !preset) {
    dateFrom = addDaysIso(today, -1);
    dateTo = today;
  } else if (preset === 'today') {
    dateFrom = today;
    dateTo = today;
  } else if (preset === 'yesterday') {
    dateFrom = addDaysIso(today, -1);
    dateTo = addDaysIso(today, -1);
  }
  const params = {date_from: dateFrom, date_to: dateTo, sort: 'newest'};
  const client = document.getElementById('reportingClientFilter')?.value || '';
  if (client) params.client = client;
  return params;
}

async function loadReportingRecruiterOptions() {
  const sel = document.getElementById('reportingRecruiterFilter');
  if (!sel || reportingRecruitersLoaded) return;
  const currentValue = sel.value;
  try {
    const rows = await fetch('/api/team?active_only=1').then(r => r.json());
    const recruiters = [...new Map((Array.isArray(rows) ? rows : []).filter(r => r.email).map(r => [String(r.email).toLowerCase(), r])).values()];
    sel.innerHTML = '<option value="">All Recruiters</option>';
    recruiters.forEach(r => {
      const opt = document.createElement('option');
      opt.value = String(r.email || '').toLowerCase();
      opt.textContent = r.name || r.email;
      opt.selected = currentValue && opt.value === currentValue;
      sel.appendChild(opt);
    });
    reportingRecruitersLoaded = true;
  } catch(e) {
    console.error('Unable to load reporting recruiters', e);
  }
}

function updateReportingDateLabels() {
  const fromInput = document.getElementById('reportingDateFromFilter');
  const toInput = document.getElementById('reportingDateToFilter');
  if (fromInput) fromInput.value = reportingDateFrom || '';
  if (toInput) toInput.value = reportingDateTo || '';
}

function setReportingPreset(preset) {
  reportingDatePreset = preset || '';
  hideReportingDateFilters();
  const today = isoDateLocal(new Date());
  if (preset === 'today') {
    reportingDateFrom = today;
    reportingDateTo = today;
  } else if (preset === 'yesterday') {
    reportingDateFrom = addDaysIso(today, -1);
    reportingDateTo = addDaysIso(today, -1);
  } else {
    reportingDateFrom = '';
    reportingDateTo = '';
  }
  document.querySelectorAll('.reporting-actions .btn-outline').forEach(btn => btn.classList.remove('active'));
  const activeBtn = document.getElementById(preset === 'today' ? 'reportingTodayBtn' : 'reportingYesterdayBtn');
  if (activeBtn) activeBtn.classList.add('active');
  updateReportingDateLabels();
  loadReportingCandidates();
}

function setReportingCustomRange() {
  hideReportingDateFilters();
  const fromInput = document.getElementById('reportingDateFromFilter');
  const toInput = document.getElementById('reportingDateToFilter');
  const fromValue = fromInput?.value || '';
  const toValue = toInput?.value || '';
  if (!fromValue || !toValue) return;
  reportingDatePreset = '';
  if (fromValue > toValue) {
    reportingDateFrom = toValue;
    reportingDateTo = fromValue;
  } else {
    reportingDateFrom = fromValue;
    reportingDateTo = toValue;
  }
  document.querySelectorAll('#reportingTodayBtn, #reportingYesterdayBtn').forEach(btn => btn.classList.remove('active'));
  updateReportingDateLabels();
  loadReportingCandidates();
}

function ensureDailyReportCcPlacement() {
  const modalBody = document.querySelector('#dailyReportModal .daily-report-body');
  const ccField = document.getElementById('dailyReportCcField');
  if (!modalBody || !ccField) return;
  ccField.style.display = 'grid';
  if (ccField.parentElement !== modalBody) {
    modalBody.insertBefore(ccField, document.getElementById('dailyReportColumnsPanel') || null);
  }
}

function reportingSelectedIds() {
  return [...document.querySelectorAll('.reporting-checkbox:checked')]
    .map(cb => cb.dataset.id)
    .filter(Boolean);
}

function updateReportingSummary(totalCount) {
  const summary = document.getElementById('reportingSummary');
  if (!summary) return;
  const selected = reportingSelectedIds().length;
  const filters = reportingFilterParams();
  if (!filters.date_from || !filters.date_to) {
    summary.textContent = `Choose Today or Yesterday to load candidates. ${selected} selected for email.`;
    return;
  }
  const dayLabel = filters.date_from === filters.date_to ? filters.date_from : `${filters.date_from} to ${filters.date_to}`;
  const client = document.getElementById('reportingClientFilter')?.selectedOptions?.[0]?.textContent || '';
  const clientLabel = client && client !== 'All Clients' ? `, client ${client}` : '';
  summary.textContent = `${totalCount || 0} candidate${totalCount === 1 ? '' : 's'} from ${dayLabel}${clientLabel}. ${selected} selected for email.`;
}

const reportingColumns = [
  {key:'name', label:'Name', value:c => c.candidate_name || '-'},
  {key:'designation', label:'Designation', value:c => c.current_role || '-'},
  {key:'company', label:'Current Company', className:'reporting-col-company', value:c => c.current_company || '-'},
  {key:'current_location', label:'Current Location', className:'reporting-col-location', value:c => c.current_location || '-'},
  {key:'preferred_location', label:'Preferred Location', className:'reporting-col-preferred-location', value:c => c.preferred_location || '-'},
  {key:'requirement', label:'Requirement', value:c => c.requirement_title || c.role_name || '-'},
  {key:'client', label:'Client', value:c => c.client_name || '-'},
  {key:'status', label:'Status', value:c => c.status || 'New'},
  {key:'recruiter', label:'Recruiter', value:c => c.recruiter_name || '-'},
  {key:'date', label:'Date', value:c => c.created_at ? c.created_at.split(' ')[0] : '-'}
];

function getReportingColumn(key) {
  return reportingColumns.find(col => col.key === key);
}

function reportingCellValue(row, key) {
  const col = getReportingColumn(key);
  return col ? String(col.value(row) || '') : '';
}

function reportingFieldOptions(selected='') {
  return reportingColumns.map(col => `<option value="${col.key}" ${selected === col.key ? 'selected' : ''}>${escapeHtml(col.label)}</option>`).join('');
}

function reportingFilterEntries() {
  return Object.entries(reportingViewState.filters).filter(([, value]) => String(value || '').trim());
}

function reportingVisibleRows() {
  let rows = [...reportingRows];
  reportingFilterEntries().forEach(([key, value]) => {
    const q = String(value).toLowerCase();
    rows = rows.filter(row => reportingCellValue(row, key).toLowerCase().includes(q));
  });
  const sortCol = getReportingColumn(reportingViewState.sortBy);
  if (sortCol) {
    rows.sort((a, b) => {
      const av = reportingCellValue(a, sortCol.key).toLowerCase();
      const bv = reportingCellValue(b, sortCol.key).toLowerCase();
      return reportingViewState.sortDir === 'desc' ? bv.localeCompare(av) : av.localeCompare(bv);
    });
  }
  return rows;
}

function renderReportingTable() {
  const table = document.getElementById('reportingCandidatesTable');
  if (!table) return;
  const data = reportingVisibleRows();
  window.reportingCandidateCount = data.length;
  const filterCount = reportingFilterEntries().length;
  const filterBtn = document.getElementById('reportingFilterBtn');
  if (filterBtn) {
    filterBtn.classList.toggle('active', Boolean(filterCount));
    filterBtn.textContent = filterCount ? `Filter (${filterCount})` : 'Filter';
  }
  if (!data.length) {
    table.innerHTML = '<tbody><tr><td class="reporting-empty">No candidates found for this view.</td></tr></tbody>';
    updateReportingSummary(0);
    return;
  }
  const sortHead = (key, label, extraClass='') => {
    const active = reportingViewState.sortBy === key;
    const mark = active ? (reportingViewState.sortDir === 'asc' ? ' ^' : ' v') : '';
    return `<th class="reporting-sort-head ${extraClass} ${active ? 'active' : ''}" onclick="sortReportingByColumn('${key}')">${escapeHtml(label)}${mark}</th>`;
  };
  table.innerHTML = `<thead><tr>
    <th style="width:44px"><input type="checkbox" onchange="toggleReportingSelection(this.checked)" title="Select all candidates"></th>
    ${sortHead('name', 'Name')}${sortHead('designation', 'Designation', 'reporting-col-designation')}${sortHead('company', 'Current Company', 'reporting-col-company')}${sortHead('current_location', 'Current Location', 'reporting-col-location')}${sortHead('preferred_location', 'Preferred Location', 'reporting-col-preferred-location')}${sortHead('requirement', 'Requirement')}${sortHead('client', 'Client')}${sortHead('status', 'Status')}${sortHead('recruiter', 'Recruiter')}${sortHead('date', 'Date')}
  </tr></thead><tbody>${data.map(c => `
    <tr onclick="const cb=this.querySelector('.reporting-checkbox'); if(cb){cb.checked=!cb.checked; updateReportingSummary(window.reportingCandidateCount || 0);}">
      <td onclick="event.stopPropagation()"><input type="checkbox" class="reporting-checkbox" data-id="${c.id}" onchange="updateReportingSummary(window.reportingCandidateCount || 0)"></td>
      <td><span class="candidate-name-link">${escapeHtml(c.candidate_name || '-')}</span><span class="candidate-subtext">${escapeHtml(c.email_addr || '')}</span></td>
      <td class="reporting-col-designation">${escapeHtml(c.current_role || '-')}</td>
      <td class="reporting-col-company">${escapeHtml(c.current_company || '-')}</td>
      <td class="reporting-col-location">${escapeHtml(c.current_location || '-')}</td>
      <td class="reporting-col-preferred-location">${escapeHtml(c.preferred_location || '-')}</td>
      <td>${escapeHtml(c.requirement_title || c.role_name || '-')}</td>
      <td>${escapeHtml(c.client_name || '-')}</td>
      <td><span class="status ${statusClassName(c.status)}">${escapeHtml(c.status || 'New')}</span></td>
      <td>${escapeHtml(c.recruiter_name || '-')}</td>
      <td>${c.created_at ? escapeHtml(c.created_at.split(' ')[0]) : '-'}</td>
    </tr>`).join('')}</tbody>`;
  updateReportingSummary(data.length);
}

function toggleReportingViewPopover(type) {
  const popover = document.getElementById('reportingViewPopover');
  if (!popover) return;
  if (popover.dataset.type === type && popover.classList.contains('active')) {
    popover.classList.remove('active');
    return;
  }
  popover.dataset.type = type;
  popover.innerHTML = reportingPopoverHtml(type);
  popover.classList.add('active');
}

function refreshReportingViewPopover(type) {
  const popover = document.getElementById('reportingViewPopover');
  if (!popover || !popover.classList.contains('active')) return;
  popover.dataset.type = type;
  popover.innerHTML = reportingPopoverHtml(type);
}

function closeReportingViewPopover() {
  const popover = document.getElementById('reportingViewPopover');
  if (popover) popover.classList.remove('active');
}

function reportingPopoverHtml(type) {
  if (type === 'sort') {
    return `<h3>Sort records</h3>
      <div class="dashboard-control-grid">
        <label>Sort by</label>
        <select onchange="setReportingSort(this.value, reportingViewState.sortDir)">${reportingFieldOptions(reportingViewState.sortBy)}</select>
        <select onchange="setReportingSort(reportingViewState.sortBy, this.value)"><option value="asc" ${reportingViewState.sortDir === 'asc' ? 'selected' : ''}>Ascending</option><option value="desc" ${reportingViewState.sortDir === 'desc' ? 'selected' : ''}>Descending</option></select>
      </div>`;
  }
  const entries = (reportingViewState.filterDrafts && reportingViewState.filterDrafts.length) ? reportingViewState.filterDrafts : reportingFilterEntries();
  return `<div class="popover-head"><h3>Filter records</h3><button class="popover-close" type="button" onclick="closeReportingViewPopover()">x</button></div>
    <div class="dashboard-filter-list" id="reportingFilterList">
      ${(entries.length ? entries : [['name', '']]).map(([key, value]) => reportingFilterRowHtml(key, value)).join('')}
    </div>
    <div style="display:flex;gap:8px;margin-top:10px;justify-content:space-between">
      <button class="dashboard-tool active" onclick="addReportingFilterRow()">Add filter</button>
      <button class="dashboard-tool" onclick="clearReportingFilters()">Clear filters</button>
    </div>`;
}

function reportingFilterRowHtml(key, value) {
  return `<div class="dashboard-filter-row">
    <select onchange="updateReportingFiltersFromPopover()">${reportingFieldOptions(key)}</select>
    <input value="${escapeHtml(value)}" placeholder="Contains..." oninput="updateReportingFilterValue(this)">
    <button class="dashboard-tool" onclick="removeReportingFilterRow(this)">Remove</button>
  </div>`;
}

function readReportingFilterRows() {
  const filters = {};
  const drafts = [];
  document.querySelectorAll('#reportingFilterList .dashboard-filter-row').forEach(row => {
    const key = row.querySelector('select')?.value || '';
    const value = row.querySelector('input')?.value || '';
    if (key) drafts.push([key, value]);
    if (key && value.trim()) filters[key] = value.trim();
  });
  reportingViewState.filters = filters;
  reportingViewState.filterDrafts = drafts.length ? drafts : [['name', '']];
}

function updateReportingFiltersFromPopover() {
  readReportingFilterRows();
  renderReportingTable();
}

function updateReportingFilterValue(input) {
  const row = input.closest('.dashboard-filter-row');
  const rowIndex = row ? Array.from(row.parentElement.children).indexOf(row) : 0;
  const cursorPos = input.selectionStart ?? input.value.length;
  readReportingFilterRows();
  renderReportingTable();
  refreshReportingViewPopover('filters');
  const activeInput = document.querySelectorAll('#reportingFilterList .dashboard-filter-row input')[rowIndex];
  if (activeInput) {
    activeInput.focus();
    activeInput.setSelectionRange(cursorPos, cursorPos);
  }
}

function addReportingFilterRow() {
  const list = document.getElementById('reportingFilterList');
  list?.insertAdjacentHTML('beforeend', reportingFilterRowHtml('name', ''));
  readReportingFilterRows();
}

function removeReportingFilterRow(button) {
  button.closest('.dashboard-filter-row')?.remove();
  readReportingFilterRows();
  renderReportingTable();
  refreshReportingViewPopover('filters');
}

function clearReportingFilters() {
  reportingViewState.filters = {};
  reportingViewState.filterDrafts = [['name', '']];
  renderReportingTable();
  refreshReportingViewPopover('filters');
}

function setReportingSort(key, dir) {
  reportingViewState.sortBy = key || 'date';
  reportingViewState.sortDir = dir || 'asc';
  renderReportingTable();
  refreshReportingViewPopover('sort');
}

function sortReportingByColumn(key) {
  if (reportingViewState.sortBy === key) {
    reportingViewState.sortDir = reportingViewState.sortDir === 'asc' ? 'desc' : 'asc';
  } else {
    reportingViewState.sortBy = key || 'date';
    reportingViewState.sortDir = key === 'date' ? 'desc' : 'asc';
  }
  renderReportingTable();
}

function toggleReportingSelection(checked) {
  document.querySelectorAll('.reporting-checkbox').forEach(cb => { cb.checked = checked; });
  updateReportingSummary(window.reportingCandidateCount || 0);
}

function exportSelectedReportingCandidates() {
  const ids = reportingSelectedIds();
  if (!ids.length) {
    showToast('Select at least one candidate to export.', 'error');
    return;
  }
  const params = new URLSearchParams({ids: ids.join(',')});
  window.location.href = '/api/candidates/daily_report_export?' + params.toString();
}

async function loadReportingCandidates() {
  const table = document.getElementById('reportingCandidatesTable');
  if (!table) return;
  if (!reportingDatePreset && !reportingDateFrom && !reportingDateTo) {
    reportingDatePreset = 'today';
    reportingDateFrom = isoDateLocal(new Date());
    reportingDateTo = reportingDateFrom;
  }
  table.innerHTML = '<tbody><tr><td class="reporting-empty">Loading candidates...</td></tr></tbody>';
  try {
    updateReportingDateLabels();
    const paramsObj = reportingFilterParams();
    const params = new URLSearchParams(paramsObj);
    params.set('all', '1');
    params.set('view', 'reporting');
    const cacheKey = JSON.stringify(paramsObj);
    if (reportingRowsCache[cacheKey]) {
      reportingRows = reportingRowsCache[cacheKey];
      renderReportingTable();
      return;
    }
    const res = await fetch('/api/candidates?' + params.toString());
    if (!res.ok) throw new Error('Unable to load candidates.');
    const rows = await res.json();
    const data = candidateRowsFromResponse(rows);
    reportingRows = data;
    reportingRowsCache[cacheKey] = data;
    renderReportingTable();
  } catch(e) {
    table.innerHTML = `<tbody><tr><td class="reporting-empty">${escapeHtml(e.message || 'Unable to load candidates.')}</td></tr></tbody>`;
  }
}

function activeCandidateFiltersObject() {
  return Object.fromEntries(buildCandidateFilterParams(false).entries());
}

function validEmailAddress(value) {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(String(value || '').trim());
}

function setDailyReportAlert(message, type='error') {
  const alertBox = document.getElementById('dailyReportAlert');
  if (!alertBox) return;
  alertBox.textContent = message || '';
  alertBox.style.display = message ? 'block' : 'none';
  alertBox.style.background = type === 'success' ? '#1f3a2a' : '#4a2b2b';
  alertBox.style.color = type === 'success' ? '#b7f0c6' : '#ffb3b3';
}

function resetDailyReportPreview() {
  window.dailyReportPreviewKey = '';
  const panel = document.getElementById('dailyReportPreviewPanel');
  if (panel) panel.style.display = 'none';
  const meta = document.getElementById('dailyReportPreviewMeta');
  if (meta) meta.textContent = '';
  const subject = document.getElementById('dailyReportPreviewSubject');
  if (subject) subject.textContent = '';
  const body = document.getElementById('dailyReportPreviewBody');
  if (body) body.innerHTML = '';
}

const dailyReportColumnCatalog = [
  {key:'name', label:'Name'},
  {key:'designation', label:'Current Designation'},
  {key:'current_company', label:'Current Company'},
  {key:'current_location', label:'Current Location'},
  {key:'preferred_location', label:'Preferred Location'},
  {key:'requirement', label:'Requirement'},
  {key:'client', label:'Client'},
  {key:'email', label:'Email-Id'},
  {key:'phone', label:'Phone'},
  {key:'experience', label:'Experience'},
  {key:'key_skills', label:'Key Skills'},
  {key:'current_salary', label:'Current Salary'},
  {key:'expected_salary', label:'Expected Salary'},
  {key:'notice_period', label:'Notice Period'},
  {key:'qualification', label:'Qualification'},
  {key:'status', label:'Status'},
  {key:'recruiter', label:'Recruiter'},
  {key:'location', label:'Location'}
];
const defaultDailyReportColumns = ['name','current_company','designation','requirement','email','phone','experience','current_salary','expected_salary','notice_period'];

function getDailyReportColumns() {
  try {
    const saved = JSON.parse(localStorage.getItem('hrguru_daily_report_columns') || '[]');
    const valid = new Set(dailyReportColumnCatalog.map(col => col.key));
    const selected = saved.filter(key => valid.has(key));
    if (selected.length) {
      const normalized = selected.filter(key => key !== 'date');
      if (!normalized.includes('current_company')) {
        const designationIndex = normalized.indexOf('designation');
        normalized.splice(designationIndex >= 0 ? designationIndex : 1, 0, 'current_company');
      }
      return normalized;
    }
    return defaultDailyReportColumns.slice();
  } catch(e) {
    return defaultDailyReportColumns.slice();
  }
}

function setDailyReportColumns(columns) {
  localStorage.setItem('hrguru_daily_report_columns', JSON.stringify(columns));
  resetDailyReportPreview();
  renderDailyReportColumnsPanel();
}

function renderDailyReportColumnsPanel() {
  const panel = document.getElementById('dailyReportColumnsPanel');
  if (!panel) return;
  const selected = getDailyReportColumns();
  const selectedSet = new Set(selected);
  const ordered = [
    ...selected.map(key => dailyReportColumnCatalog.find(col => col.key === key)).filter(Boolean),
    ...dailyReportColumnCatalog.filter(col => !selectedSet.has(col.key))
  ];
  panel.innerHTML = '<div class="muted" style="font-size:12px;margin-bottom:8px">Date is always included as the first column.</div>' + ordered.map((col, index) => {
    const checked = selectedSet.has(col.key);
    const selectedIndex = selected.indexOf(col.key);
    return `<div style="display:grid;grid-template-columns:auto minmax(0,1fr) auto auto;gap:8px;align-items:center;padding:6px 0;border-bottom:1px solid #242a3a">
      <input type="checkbox" ${checked ? 'checked' : ''} onchange="toggleDailyReportColumn('${col.key}', this.checked)" style="width:auto">
      <span style="color:#d9dee8;font-size:13px">${escapeHtml(col.label)}</span>
      <button class="dashboard-tool" type="button" onclick="moveDailyReportColumn('${col.key}', -1)" ${selectedIndex <= 0 ? 'disabled' : ''}>Up</button>
      <button class="dashboard-tool" type="button" onclick="moveDailyReportColumn('${col.key}', 1)" ${!checked || selectedIndex === selected.length - 1 ? 'disabled' : ''}>Down</button>
    </div>`;
  }).join('') + '<div class="muted" style="font-size:12px;margin-top:8px">Checked columns appear in the email in this order.</div>';
}

function toggleDailyReportColumnsPanel() {
  const panel = document.getElementById('dailyReportColumnsPanel');
  if (!panel) return;
  renderDailyReportColumnsPanel();
  panel.style.display = panel.style.display === 'none' || !panel.style.display ? 'block' : 'none';
}

function toggleDailyReportColumn(key, checked) {
  const selected = getDailyReportColumns();
  if (checked && !selected.includes(key)) selected.push(key);
  if (!checked && selected.includes(key)) selected.splice(selected.indexOf(key), 1);
  if (!selected.length) selected.push('name');
  setDailyReportColumns(selected);
}

function moveDailyReportColumn(key, direction) {
  const selected = getDailyReportColumns();
  const index = selected.indexOf(key);
  const next = index + direction;
  if (index < 0 || next < 0 || next >= selected.length) return;
  [selected[index], selected[next]] = [selected[next], selected[index]];
  setDailyReportColumns(selected);
}

function currentDailyReportPayload() {
  const mode = window.dailyReportMode || 'report';
  const source = window.dailyReportSource || 'candidates';
  const ids = source === 'reporting' ? reportingSelectedIds() : getSelectedCandidateIds();
  const filters = source === 'reporting' ? reportingFilterParams() : activeCandidateFiltersObject();
  const email = document.getElementById('dailyReportEmail')?.value.trim() || '';
  const columns = getDailyReportColumns();
  return {mode, source, ids, filters, email, columns};
}

function buildDailyReportPreviewKey(payload) {
  return JSON.stringify({
    mode: payload.mode,
    to: payload.email,
    cc: payload.cc,
    columns: payload.columns,
    ids: payload.ids,
    filters: payload.filters
  });
}

function setDailyReportSendState(isSending, mode='report') {
  const sendBtn = document.getElementById('dailyReportSendBtn');
  const label = mode === 'feedback' ? 'Send Feedback Request' : 'Send Daily Submission';
  if (sendBtn) {
    sendBtn.disabled = Boolean(isSending);
    sendBtn.textContent = isSending ? 'Sending...' : label;
  }
}

async function openDailyReportModal(source='candidates') {
  const modal = document.getElementById('dailyReportModal');
  if (!modal) return;
  modal.classList.add('active');
  window.dailyReportMode = 'report';
  resetDailyReportPreview();
  try {
    ensureDailyReportCcPlacement();
    const selectedIds = source === 'reporting' ? reportingSelectedIds() : getSelectedCandidateIds();
    if (source === 'reporting' && !selectedIds.length) {
      showToast('Select at least one candidate for the daily report.', 'error');
      closeModal('dailyReportModal');
      return;
    }
    const openBtn = document.getElementById('openDailyReportBtn');
    if (openBtn) openBtn.disabled = true;
    const filters = source === 'reporting' ? reportingFilterParams() : activeCandidateFiltersObject();
    const filterCount = Object.keys(filters).length;
    const summary = document.getElementById('dailyReportSummary');
    if (summary) {
      summary.textContent = selectedIds.length
        ? `${selectedIds.length} selected candidate${selectedIds.length === 1 ? '' : 's'} will be included.`
        : filterCount
          ? 'Candidates matching the current filters will be included.'
          : 'All visible candidates available to you will be included.';
    }
    window.dailyReportSource = source;
    const title = document.getElementById('dailyReportModalTitle');
    if (title) title.textContent = 'Send Daily Submission Email';
    const columnsPanel = document.getElementById('dailyReportColumnsPanel');
    if (columnsPanel) columnsPanel.style.display = 'none';
    renderDailyReportColumnsPanel();
    const ccField = document.getElementById('dailyReportCcField');
    if (ccField) ccField.style.display = '';
    const sendBtn = document.getElementById('dailyReportSendBtn');
    if (sendBtn) sendBtn.textContent = 'Send Daily Submission';
    setDailyReportAlert('');
    const input = document.getElementById('dailyReportEmail');
    if (input) input.value = localStorage.getItem('hrguru_daily_report_email') || '';
    const ccInput = document.getElementById('dailyReportCc');
    if (ccInput) ccInput.value = localStorage.getItem('hrguru_daily_report_cc') || '';
    loadDailyReportEmailPresetOptions();
    setTimeout(() => input && input.focus(), 50);
  } catch (e) {
    console.error('openDailyReportModal failed', e);
    setDailyReportAlert(e?.message || 'Unable to open daily report modal.');
  }
}

async function openFeedbackRequestModal() {
  const modal = document.getElementById('dailyReportModal');
  if (!modal) return;
  modal.classList.add('active');
  const selectedIds = reportingSelectedIds();
  if (!selectedIds.length) {
    showToast('Select at least one candidate before requesting feedback.', 'error');
    closeModal('dailyReportModal');
    return;
  }
  window.dailyReportMode = 'feedback';
  window.dailyReportSource = 'reporting';
  resetDailyReportPreview();
  try {
    ensureDailyReportCcPlacement();
    const title = document.getElementById('dailyReportModalTitle');
    if (title) title.textContent = 'Request Candidate Feedback';
    const columnsPanel = document.getElementById('dailyReportColumnsPanel');
    if (columnsPanel) columnsPanel.style.display = 'none';
    renderDailyReportColumnsPanel();
    const summary = document.getElementById('dailyReportSummary');
    if (summary) summary.textContent = `${selectedIds.length} selected candidate${selectedIds.length === 1 ? '' : 's'} will be included in the feedback request.`;
    const ccField = document.getElementById('dailyReportCcField');
    if (ccField) ccField.style.display = 'none';
    const emailInput = document.getElementById('dailyReportEmail');
    if (emailInput) emailInput.value = localStorage.getItem('hrguru_feedback_email') || '';
    const ccInput = document.getElementById('dailyReportCc');
    if (ccInput) ccInput.value = '';
    loadDailyReportEmailPresetOptions();
    const sendBtn = document.getElementById('dailyReportSendBtn');
    if (sendBtn) sendBtn.textContent = 'Send Feedback Request';
    setDailyReportAlert('');
    setTimeout(() => emailInput && emailInput.focus(), 50);
  } catch (e) {
    console.error('openFeedbackRequestModal failed', e);
    setDailyReportAlert(e?.message || 'Unable to open feedback request modal.');
  }
}

async function previewDailyReportEmail() {
  const payload = currentDailyReportPayload();
  if (payload.mode === 'feedback' && !payload.ids.length) {
    setDailyReportAlert('Select at least one candidate before previewing feedback request.');
    return false;
  }
  if (payload.email && !validEmailAddress(payload.email)) {
    setDailyReportAlert('Please enter a valid email address.');
    return false;
  }
  const ccRaw = document.getElementById('dailyReportCc')?.value || '';
  const ccList = validateEmailList(ccRaw);
  if (ccList === null) {
    setDailyReportAlert('Please enter valid CC email addresses separated by commas or line breaks.');
    return false;
  }
  const btn = document.getElementById('dailyReportPreviewBtn');
  if (btn) {
    btn.disabled = true;
    btn.textContent = 'Previewing...';
  }
  setDailyReportAlert('');
  try {
    const endpoint = payload.mode === 'feedback'
      ? '/api/candidates/feedback_request_preview'
      : '/api/candidates/daily_report_preview';
    const res = await fetch(endpoint, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({
      to: payload.email,
      cc: ccList || [],
      columns: payload.columns,
      ids: payload.ids,
      filters: payload.filters
    })
  });
    const data = await res.json().catch(() => ({}));
    if (!res.ok || data.error) throw new Error(data.error || 'Unable to preview email.');
    const panel = document.getElementById('dailyReportPreviewPanel');
    const meta = document.getElementById('dailyReportPreviewMeta');
    const subject = document.getElementById('dailyReportPreviewSubject');
    const body = document.getElementById('dailyReportPreviewBody');
    if (meta) {
      const cvList = Array.isArray(data.cv_filenames) && data.cv_filenames.length ? ` (${data.cv_filenames.join(', ')})` : '';
      const ccText = Array.isArray(ccList) && ccList.length ? `, CC: ${ccList.join(', ')}` : '';
      meta.textContent = `${data.count || 0} candidate${data.count === 1 ? '' : 's'} included - ${data.attached_cvs || 0} CV file${data.attached_cvs === 1 ? '' : 's'} will be attached${cvList}${ccText}`;
    }
    if (subject) subject.textContent = `Subject: ${data.subject || ''}`;
    if (body) body.innerHTML = data.html_body || `<pre style="white-space:pre-wrap;margin:0">${escapeHtml(data.body || '')}</pre>`;
    if (panel) panel.style.display = 'block';
    window.dailyReportPreviewKey = buildDailyReportPreviewKey(payload);
    if (Array.isArray(data.missing_cvs) && data.missing_cvs.length) {
      setDailyReportAlert(`Cannot send yet. Attach required CVs first. Missing CV for: ${data.missing_cvs.join(', ')}.`);
    } else {
      setDailyReportAlert('Preview ready. Review it, then click Send.', 'success');
    }
    return true;
  } catch(e) {
    setDailyReportAlert(e.message || 'Unable to preview email.');
    return false;
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.textContent = 'Preview';
    }
  }
}

async function sendDailyReportEmail() {
  const email = document.getElementById('dailyReportEmail').value.trim();
  if (!validEmailAddress(email)) {
    setDailyReportAlert('Please enter a valid email address.');
    return;
  }
  if (window.dailyReportSubmitting) {
    setDailyReportAlert('This report is already being sent. Please wait a moment.');
    return;
  }
  const btn = document.getElementById('dailyReportSendBtn');
  const mode = window.dailyReportMode || 'report';
  const source = window.dailyReportSource || 'candidates';
  const ids = source === 'reporting' ? reportingSelectedIds() : getSelectedCandidateIds();
  const filters = source === 'reporting' ? reportingFilterParams() : activeCandidateFiltersObject();
  const ccRaw = document.getElementById('dailyReportCc')?.value || '';
  const ccList = validateEmailList(ccRaw);
  if (ccList === null) {
    setDailyReportAlert('Please enter valid CC email addresses separated by commas or line breaks.');
    return;
  }
  const columns = getDailyReportColumns();
  const payload = {mode, source, ids, filters, email, cc: ccList || [], columns};
  window.dailyReportSubmitting = true;
  setDailyReportSendState(true, mode);
  btn.disabled = true;
  setDailyReportAlert('');
  try {
    const preflightEndpoint = mode === 'feedback' ? '/api/candidates/feedback_request_preview' : '/api/candidates/daily_report_preview';
    const preflightRes = await fetch(preflightEndpoint, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        to: payload.email,
        cc: payload.cc,
        columns: payload.columns,
        ids: payload.ids,
        filters: payload.filters
      })
    });
    const preflightData = await preflightRes.json().catch(() => ({}));
    if (!preflightRes.ok || preflightData.error) throw new Error(preflightData.error || 'Unable to validate email before sending.');
    if (Array.isArray(preflightData.missing_cvs) && preflightData.missing_cvs.length) {
      throw new Error(`Cannot send yet. Attach required CVs first. Missing CV for: ${preflightData.missing_cvs.join(', ')}.`);
    }
    const endpoint = mode === 'feedback' ? '/api/candidates/feedback_request_email' : '/api/candidates/daily_report_email';
    const res = await fetch(endpoint, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({to: email, cc: ccList || [], columns, ids, filters})
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok || data.error) throw new Error(data.error || (mode === 'feedback' ? 'Unable to send feedback request.' : 'Unable to send daily work report.'));
    if (mode === 'feedback') {
      localStorage.setItem('hrguru_feedback_email', email);
    } else {
      localStorage.setItem('hrguru_daily_report_email', email);
      localStorage.setItem('hrguru_daily_report_cc', (ccList || []).join(', '));
    }
    setDailyReportAlert(data.message || (mode === 'feedback' ? 'Feedback request sent successfully.' : 'Daily submission email sent successfully.'), 'success');
    showToast(data.message || (mode === 'feedback' ? 'Feedback request sent successfully.' : 'Daily submission email sent successfully.'), 'success');
    setTimeout(() => closeModal('dailyReportModal'), 900);
  } catch(e) {
    const message = e.message || (mode === 'feedback' ? 'Unable to send feedback request.' : 'Unable to send daily work report.');
    setDailyReportAlert(message);
    showToast(message, 'error', 7000);
  } finally {
    window.dailyReportSubmitting = false;
    setDailyReportSendState(false, mode);
    const openBtn = document.getElementById('openDailyReportBtn');
    if (openBtn) openBtn.disabled = false;
  }
}

function toggleViewMode() {
  const mode = document.getElementById('viewMode').value;
  localStorage.setItem('hrguru_view_mode', mode);
  loadCandidates();
}

function toggleSelectAllRows() {
  const checked = document.getElementById('selectAllHeader').checked;
  document.querySelectorAll('.row-checkbox').forEach(cb => cb.checked = checked);
  updateBulkBtn();
}

function statusClassName(status) {
  return 'status-' + String(status || 'New').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');
}

function applyStatusClass(select) {
  if (!select) return;
  Array.from(select.classList).forEach(cls => {
    if (cls.startsWith('status-')) select.classList.remove(cls);
  });
  select.classList.add(statusClassName(select.value));
}

async function bulkDeleteCurrentPage() {
  const checkedCards = document.querySelectorAll('.card-checkbox:checked');
  const checkedRows = document.querySelectorAll('.row-checkbox:checked');

  const ids = Array.from(checkedCards).map(cb => cb.closest('.candidate-card')?.dataset?.id)
    .concat(Array.from(checkedRows).map(cb => cb.dataset?.id))
    .filter(Boolean);

  if (!ids.length) {
    showToast('Please select candidates first using checkboxes', 'error');
    return;
  }

  const ok = await confirmAction({
    title: 'Delete selected candidates?',
    message: 'This will delete ' + ids.length + ' selected candidate' + (ids.length > 1 ? 's' : '') + '.',
    okText: 'Delete'
  });
  if (!ok) return;

  try {
    const res = await fetch('/api/candidates/bulk_delete', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ids})
    });

    const data = await res.json();

    if (data.ok) {
      loadDashboardCandidateList();
      loadCandidateStats();
      showToast('Deleted ' + ids.length + ' candidate' + (ids.length > 1 ? 's' : ''), 'success');
    }

  } catch(e) {
    showToast('Error: ' + e.message, 'error');
  }
}

async function loadJobs() {
  const rows = await fetch('/api/jobs').then(r => r.json());
  if (!rows.length) { document.getElementById('jobsList').innerHTML = '<div class="no-data">No jobs found</div>'; return; }
  document.getElementById('jobsList').innerHTML = rows.map(j => `<div style="background:#1c2030;padding:16px;border-radius:8px;margin-bottom:12px;border:1px solid #2a2f3a">
    <div style="display:flex;justify-content:space-between;align-items:center">
      <div><span style="font-size:14px;font-weight:600">${j.title}</span> <span class="tag">${j.job_id}</span> <span class="status ${j.status}">${j.status}</span></div>
      <div><button class="action-btn" onclick="deleteJob(${j.id})">Delete</button></div>
    </div>
    <div style="color:#6b7494;font-size:12px;margin-top:8px">${j.client_name||''} | ${j.location||''} | ${j.remote?'Remote':''}</div>
  </div>`).join('');
}

function showAddJobModal() {
  ['jobTitle','jobClient','jobLocation','jobDescription','jobPrimarySkills','jobExperience','jobBillRate','jobPayRate'].forEach(id => setValue(id, ''));
  setValue('jobOpenings', '1');
  setValue('jobType', 'Full-time');
  setValue('jobPriority', 'Medium');
  showModal('jobModal');
}

async function saveJob() {
  const descriptionBits = [
    valueOf('jobDescription'),
    'Type: ' + valueOf('jobType'),
    'Priority: ' + valueOf('jobPriority'),
    'Openings: ' + valueOf('jobOpenings'),
    'Primary Skills: ' + valueOf('jobPrimarySkills'),
    'Experience: ' + valueOf('jobExperience'),
    'Client Bill Rate / Salary: ' + valueOf('jobBillRate'),
    'Pay Rate / Salary: ' + valueOf('jobPayRate')
  ].filter(Boolean);
  const body = {title: document.getElementById('jobTitle').value, client_name: document.getElementById('jobClient').value, location: document.getElementById('jobLocation').value, description: descriptionBits.join('\n')};
  if (!body.title) { showToast('Job title is required', 'error'); return; }
  await fetch('/api/jobs', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)});
  closeModal('jobModal'); loadJobs();
}

async function deleteJob(id) {
  const ok = await confirmAction({title:'Delete job?', message:'This job will be removed.', okText:'Delete'});
  if (!ok) return;
  await fetch('/api/jobs/' + id, {method: 'DELETE'});
  loadJobs();
  showToast('Job deleted', 'success');
}


function showAddTeamModal() { document.getElementById('teamName').value=''; document.getElementById('teamEmail').value=''; document.getElementById('teamPhone').value=''; document.getElementById('teamRole').value=''; document.getElementById('teamBulkAdmin').checked=false; showModal('teamModal'); }

async function loadTeam() {
    const rows = await fetch('/api/team').then(r => r.json());
  if (!rows.length) { document.getElementById('teamTable').innerHTML = '<div class="no-data">No team members</div>'; return; }
  document.getElementById('teamTable').innerHTML = rows.map(m => `<div style="background:#1c2030;padding:16px;border-radius:8px;margin-bottom:12px;border:1px solid #2a2f3a;display:flex;justify-content:space-between;align-items:center">
    <div><strong>${m.name}</strong> <span style="color:#6b7494">${m.email}</span> <span class="tag">${m.role||'Member'}</span> ${m.can_bulk_upload?'<span class="tag">Bulk Upload</span>':''} ${m.is_ex_employee?'<span class="tag" style="background:#4b3a23;color:#ffd28a">Ex-employee</span>':''}</div>
    <div style="display:flex;gap:8px">
      ${currentUser.is_admin ? `<button class="action-btn" onclick="toggleBulkUploadAccess(${m.id}, ${m.can_bulk_upload ? 0 : 1})">${m.can_bulk_upload ? 'Remove Bulk' : 'Grant Bulk'}</button>` : ''}
      <button class="action-btn" onclick="deleteTeamMember(${m.id})">Delete</button>
    </div>
  </div>`).join('');
}

async function toggleBulkUploadAccess(id, enabled) {
  const res = await fetch(`/api/team/${id}`, {method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({can_bulk_upload: !!enabled})});
  const data = await res.json();
  if (!data.ok) showToast(data.error || 'Unable to update bulk upload access', 'error');
  loadTeam();
}

async function saveTeamMember() {
  const name = document.getElementById('teamName').value.trim();
  const email = document.getElementById('teamEmail').value.trim();
  const phone = document.getElementById('teamPhone').value.trim();
  const role = document.getElementById('teamRole').value.trim();
  const can_bulk_upload = document.getElementById('teamBulkAdmin').checked;
  if (!name || !email) { showToast('Name and Email are required', 'error'); return; }
  const res = await fetch('/api/team', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name,email,phone,role,can_bulk_upload})});
  const data = await res.json();
  if (data.ok) { closeModal('teamModal'); loadTeam(); showToast('Team member added', 'success'); } else { showToast(data.error || 'Failed to add team member', 'error'); }
}

async function bulkUploadTeam(file) {
  if (!file) return;
  const formData = new FormData();
  formData.append('file', file);
  const res = await fetch('/api/team/bulk', {method:'POST',body:formData});
  const data = await res.json();
  document.getElementById('teamBulkStatus').textContent = data.ok ? `Added ${data.added}, Skipped ${data.skipped}` : `Error: ${data.error}`;
  loadTeam();
}

async function deleteTeamMember(id) {
  const ok = await confirmAction({title:'Delete team member?', message:'This team member will be removed.', okText:'Delete'});
  if (!ok) return;
  await fetch(`/api/team/${id}`,{method:'DELETE'});
  loadTeam();
  showToast('Team member deleted', 'success');
}

async function loadUsers() {
  const rows = await fetch('/api/users').then(r => r.json());
  if (!rows.length) { document.getElementById('usersList').innerHTML = '<div class="no-data">No users</div>'; return; }
  document.getElementById('usersList').innerHTML = rows.map(u => `<div style="display:flex;justify-content:space-between;gap:16px;align-items:center;padding:14px;background:#1c2030;border:1px solid #2a2f3a;border-radius:10px;margin-bottom:10px">
    <div>
      <strong>${u.username}</strong> ${u.is_admin?'<span class="tag">Admin</span>':'<span class="tag" style="background:#3a4050">User</span>'} 
      ${u.is_bulk_admin?'<span class="tag">Bulk Upload</span>':''}
      ${u.is_active?'':'<span style="color:#e8643a;font-size:12px">(Inactive)</span>'}
      <div class="muted" style="font-size:12px;margin-top:6px">Last login: ${escapeHtml(formatLoginTime(u.last_login_at || u.team_last_login_at))}${u.team_email ? ` Â· ${escapeHtml(u.team_email)}` : ''}</div>
    </div>
    <div style="display:flex;gap:6px;flex-wrap:wrap;justify-content:flex-end">
      <button class="action-btn" onclick="toggleUserRole(${u.id}, 'is_admin', ${u.is_admin ? 0 : 1})">${u.is_admin ? 'Remove Admin' : 'Make Admin'}</button>
      <button class="action-btn" onclick="toggleUserRole(${u.id}, 'is_bulk_admin', ${u.is_bulk_admin ? 0 : 1})">${u.is_bulk_admin ? 'Remove Bulk' : 'Grant Bulk'}</button>
      <button class="action-btn" onclick="toggleUserRole(${u.id}, 'is_active', ${u.is_active ? 0 : 1})">${u.is_active ? 'Deactivate' : 'Activate'}</button>
      <button class="action-btn" onclick="resetUserPassword(${u.id}, '${escapeHtml(u.username)}')">Reset Password</button>
      <button class="action-btn" onclick="deleteUser(${u.id})">Delete</button>
    </div>
  </div>`).join('');
}

async function loadUserLoginReport() {
  const panel = document.getElementById('userLoginReport');
  if (!panel) return;
  panel.style.display = 'block';
  panel.innerHTML = '<div class="ats-panel pad">Loading login report...</div>';
  try {
    const rows = await fetch('/api/users/login_report?limit=200').then(r => r.json());
    if (!Array.isArray(rows)) throw new Error(rows.error || 'Unable to load login report');
    if (!rows.length) {
      panel.innerHTML = '<div class="ats-panel pad muted">No login activity recorded yet.</div>';
      return;
    }
    panel.innerHTML = `<div class="ats-panel pad">
      <div style="display:flex;justify-content:space-between;align-items:center;gap:12px;margin-bottom:12px">
        <h3 style="margin:0;color:#fff">User Login Report</h3>
        <button class="btn btn-outline" onclick="document.getElementById('userLoginReport').style.display='none'">Hide</button>
      </div>
      <div class="candidates-table-wrap" style="display:block;max-height:420px">
        <table class="candidates-table" style="display:table!important;width:100%">
          <thead><tr><th>Date/Time</th><th>User</th><th>Email</th><th>Role</th><th>Status</th><th>Method</th><th>IP Address</th><th>Message</th></tr></thead>
          <tbody>${rows.map(r => `<tr>
            <td>${escapeHtml(formatLoginTime(r.created_at))}</td>
            <td>${escapeHtml(r.display_name || r.username || '-')}</td>
            <td>${escapeHtml(r.email || '-')}</td>
            <td>${escapeHtml(r.role || '-')}</td>
            <td><span class="status ${String(r.status).toLowerCase()==='success' ? 'status-joined' : 'status-rejected'}">${escapeHtml(r.status || '-')}</span></td>
            <td>${escapeHtml(r.method || '-')}</td>
            <td>${escapeHtml(r.ip_address || '-')}</td>
            <td>${escapeHtml(r.message || '-')}</td>
          </tr>`).join('')}</tbody>
        </table>
      </div>
    </div>`;
  } catch(e) {
    panel.innerHTML = `<div class="ats-panel pad" style="color:#ffb3b3">${escapeHtml(e.message || 'Unable to load login report')}</div>`;
  }
}

function formatLoginTime(value) {
  if (!value) return 'Never';
  const normalized = String(value).includes('T') ? String(value) : String(value).replace(' ', 'T');
  const dt = new Date(normalized);
  if (Number.isNaN(dt.getTime())) return String(value);
  return dt.toLocaleString();
}

async function toggleUserRole(id, field, value) {
  const body = {};
  body[field] = value;
  const res = await fetch('/api/users/' + id, {
    method:'PATCH',
    headers:{'Content-Type':'application/json'},
    body:JSON.stringify(body)
  });
  const data = await res.json();
  if (data.ok) {
    showToast('User access updated', 'success');
    loadUsers();
  } else {
    showToast(data.error || 'Failed to update user', 'error');
  }
}

async function resetUserPassword(id, username) {
  const password = prompt('Enter new password for ' + username + ' (minimum 8 characters)');
  if (!password) return;
  if (password.length < 8) {
    showToast('Password must be at least 8 characters', 'error');
    return;
  }
  const res = await fetch('/api/users/' + id, {
    method:'PATCH',
    headers:{'Content-Type':'application/json'},
    body:JSON.stringify({password})
  });
  const data = await res.json();
  if (data.ok) {
    showToast('Password reset successfully', 'success');
  } else {
    showToast(data.error || 'Password reset failed', 'error');
  }
}

async function createLoginsFromTeam() {
  const ok = await confirmAction({
    title:'Create login accounts?',
    message:'This will create login accounts for team members who do not have one.',
    okText:'Create',
    danger:false
  });
  if (!ok) return;
  
  const res = await fetch('/api/users/create-from-team', {method:'POST'});
  const data = await res.json();
  
  if (data.ok) {
    let msg = `${data.total_created} login(s) created:\n\n`;
    data.created.forEach(u => {
      msg += `${u.name}\n  Username: ${u.username}\n  Password: ${u.password}\n\n`;
    });
    if (data.skipped.length) {
      msg += `\n${data.skipped.length} skipped:\n`;
      data.skipped.forEach(u => msg += `- ${u.name}: ${u.error}\n`);
    }
    showToast(msg.replace(/\n+/g, ' '), 'success', 8000);
    loadUsers();
  } else {
    showToast(data.error || 'Failed to create logins', 'error');
  }
}

function showManageUsers() { 
  document.getElementById('userUsername').value = '';
  document.getElementById('userEmail').value = '';
  document.getElementById('userPassword').value = '';
  document.getElementById('userAdmin').checked = false;
  document.getElementById('userBulkAdmin').checked = false;
  loadUsers(); showModal('userModal'); 
}

async function saveUser() {
  const body = {username: document.getElementById('userUsername').value, email: document.getElementById('userEmail').value, password: document.getElementById('userPassword').value, is_admin: document.getElementById('userAdmin').checked, is_bulk_admin: document.getElementById('userBulkAdmin').checked};
  if (!body.username || !body.password) { showToast('Username and Password are required', 'error'); return; }
  const res = await fetch('/api/users', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  const data = await res.json();
  if (data.ok) { closeModal('userModal'); loadUsers(); showToast('User added', 'success'); } else { showToast(data.error || 'Failed to add user', 'error'); }
}

async function deleteUser(id) {
  const ok = await confirmAction({title:'Delete user?', message:'This login user will be removed.', okText:'Delete'});
  if (!ok) return;
  await fetch(`/api/users/${id}`,{method:'DELETE'});
  loadUsers();
  showToast('User deleted', 'success');
}

async function loadRequirements() {
  const params = new URLSearchParams();
  params.set('page', String(requirementListPage));
  params.set('page_size', String(requirementListPageSize));
  if (requirementStatusFilter) params.set('status', requirementStatusFilter);
  const requirementQuery = valueOf('requirementsSearchInput').trim();
  if (requirementQuery) params.set('q', requirementQuery);
  const payload = await fetch('/api/requirements?' + params.toString()).then(r => r.json());
  const rows = Array.isArray(payload) ? payload : (payload.rows || []);
  if (!rows.length && payload.total && requirementListPage > 1) {
    requirementListPage = Math.max(1, Number(payload.total_pages || 1));
    return loadRequirements();
  }
  
  // Update stats
  const stats = payload.stats || {};
  const open = stats.open ?? rows.filter(r => r.status === 'Open').length;
  const inProgress = stats.in_progress ?? rows.filter(r => r.status === 'In Progress').length;
  const closed = stats.closed ?? rows.filter(r => r.status === 'Closed').length;
  const totalSubs = stats.total_submissions ?? rows.reduce((sum, r) => sum + (r.submissions || 0), 0);
  document.getElementById('reqOpenCount').textContent = open;
  document.getElementById('reqInProgressCount').textContent = inProgress;
  document.getElementById('reqClosedCount').textContent = closed;
  document.getElementById('reqTotalSubmissions').textContent = totalSubs;
  
  // Store for filtering
  window.allRequirements = rows;
  renderRequirementTitleSuggestions(rows);
  
  renderRequirementsTable(rows);
  renderPagination('requirementsPagination', Array.isArray(payload) ? {page:1,page_size:rows.length || requirementListPageSize,total:rows.length,total_pages:1} : payload, 'goToRequirementPage');
}

let requirementStatusFilter = '';

function toggleRequirementStatusMenu(event) {
  event.stopPropagation();
  const menu = document.getElementById('reqStatusMenu');
  if (menu) menu.classList.toggle('active');
}

function setRequirementStatusFilter(status) {
  requirementStatusFilter = status || '';
  requirementListPage = 1;
  const menu = document.getElementById('reqStatusMenu');
  if (menu) {
    menu.classList.remove('active');
    menu.querySelectorAll('button').forEach(btn => btn.classList.toggle('active', btn.textContent === (status || 'All Status')));
  }
  const btn = document.getElementById('reqStatusFilterBtn');
  if (btn) btn.classList.toggle('active', Boolean(requirementStatusFilter));
  loadRequirements();
}

function extractRequirementField(description, label) {
  const line = String(description || '').split(/\r?\n/).find(part =>
    part.toLowerCase().startsWith(label.toLowerCase() + ':')
  );
  return line ? line.slice(line.indexOf(':') + 1).trim() : '';
}

async function renderRequirementsTable(rows) {
  const selectAll = document.getElementById('reqSelectAll');
  if (selectAll) selectAll.checked = false;
  if (!rows.length) {
    document.getElementById('requirementsBody').innerHTML = '<tr><td colspan="6" style="text-align:center;padding:40px;color:#6b7494">No requirements found</td></tr>';
    updateReqBulkBtn();
    return;
  }
  
  document.getElementById('requirementsBody').innerHTML = rows.map(r => {
    const statusClass = r.status ? r.status.replace(/ /g, '.') : 'Open';
    const primarySkills = extractRequirementField(r.description, 'Primary Skills') || '-';
    const jdIcon = r.jd_url ? `<a href="${escapeHtml(r.jd_url)}" download class="req-jd-icon" title="Download requirement JD" onclick="event.stopPropagation()">JD</a>` : '';
    return `<tr data-id="${r.id}">
      <td onclick="event.stopPropagation()"><input type="checkbox" class="req-checkbox" onchange="updateReqBulkBtn()"></td>
      <td class="req-title"><span class="req-title-line">${escapeHtml(r.title || '-')}${jdIcon}</span><span class="req-client">${escapeHtml(r.client_name || '-')}</span></td>
      <td><span class="req-skill-text" title="${escapeHtml(primarySkills)}">${escapeHtml(primarySkills)}</span></td>
      <td>${r.sourcer_name || r.recruiter_name || '-'}</td>
      <td><span class="status-badge ${statusClass}">${r.status || 'Open'}</span></td>
      <td onclick="event.stopPropagation()">
        <button class="action-btn" onclick="editRequirement(${r.id})">Edit</button>
        <button class="action-btn delete" onclick="deleteRequirement(${r.id})">Delete</button>
      </td>
    </tr>`;
  }).join('');
  updateReqBulkBtn();
}

function toggleAllReq() {
  const checked = document.getElementById('reqSelectAll').checked;
  document.querySelectorAll('.req-checkbox').forEach(cb => cb.checked = checked);
  updateReqBulkBtn();
}

function updateReqBulkBtn() {
  const checked = document.querySelectorAll('.req-checkbox:checked').length;
  const btn = document.getElementById('reqBulkDeleteBtn');
  if (checked > 0) {
    btn.disabled = false;
    btn.style.opacity = '1';
    btn.textContent = `Delete Selected (${checked})`;
  } else {
    btn.disabled = true;
    btn.style.opacity = '0.5';
    btn.textContent = 'Delete Selected';
  }
}

async function bulkDeleteRequirements() {
  const ids = [];
  document.querySelectorAll('.req-checkbox:checked').forEach(cb => {
    ids.push(cb.closest('tr').dataset.id);
  });
  if (!ids.length) {
    showToast('Select requirements first', 'error');
    return;
  }
  const ok = await confirmAction({
    title: 'Delete selected requirements?',
    message: 'This will delete ' + ids.length + ' requirement' + (ids.length > 1 ? 's' : '') + ' and their screening checks. Existing candidates will remain in the system.',
    okText: 'Delete'
  });
  if (!ok) return;
  let deleted = 0;
  for (const id of ids) {
    const res = await fetch('/api/requirements/' + id, {method: 'DELETE'});
    if (res.ok) deleted += 1;
  }
  await loadRequirements();
  await loadFilterOptions();
  showToast('Deleted ' + deleted + ' requirement' + (deleted === 1 ? '' : 's'), deleted ? 'success' : 'error');
}

function filterRequirements() {
  requirementListPage = 1;
  loadRequirements();
}

function populateTeamDropdowns() {
  return Promise.resolve();
}

async function viewSubmissions(reqId) {
  document.getElementById('submissionsReqId').value = reqId;
  const rows = await fetch('/api/submissions').then(r => r.json());
  const filtered = rows.filter(s => s.requirement_id == reqId);
  
  let html = `<div style="padding:20px">
    <h3 style="margin:0 0 20px 0">Submissions for this Requirement</h3>`;
  
  if (!filtered.length) {
    html += '<p style="color:#6b7494">No submissions yet</p>';
  } else {
    html += `<table style="width:100%;border-collapse:collapse">
      <thead><tr style="text-align:left;color:#6b7494;font-size:12px"><th>Candidate</th><th>Email</th><th>Phone</th><th>Status</th><th>Submitted</th><th>Actions</th></tr></thead>
      <tbody>`;
    filtered.forEach(s => {
      html += `<tr style="border-bottom:1px solid #2a2f3a">
        <td style="padding:12px"><strong>${s.candidate_name || '-'}</strong></td>
        <td style="padding:12px;color:#8892b0">${s.email_addr || '-'}</td>
        <td style="padding:12px">${s.phone || '-'}</td>
        <td style="padding:12px"><span class="status ${s.status}">${s.status || 'Submitted'}</span></td>
        <td style="padding:12px;color:#6b7494">${s.submitted_at ? s.submitted_at.split(' ')[0] : '-'}</td>
        <td style="padding:12px">
          <button class="action-btn" onclick="updateSubmissionStatus(${s.id}, 'Interview Scheduled')">Schedule</button>
          <button class="action-btn" onclick="updateSubmissionStatus(${s.id}, 'Rejected')">Reject</button>
        </td>
      </tr>`;
    });
    html += '</tbody></table>';
  }
  
  html += '<button class="btn btn-outline" onclick="closeModal(\'viewSubmissionsModal\')" style="margin-top:20px">Close</button></div>';
  
  document.getElementById('viewSubmissionsContent').innerHTML = html;
  showModal('viewSubmissionsModal');
}

async function updateSubmissionStatus(subId, status) {
  await fetch('/api/submissions/' + subId, {
    method: 'PATCH',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({status})
  });
  const reqId = document.getElementById('submissionsReqId').value;
  viewSubmissions(reqId);
  loadRequirements();
}

async function editRequirement(id) {
  console.log('editRequirement called:', id);
  
  // Populate dropdowns first
  populateTeamDropdowns();
  
  const r = await fetch('/api/requirements/' + id).then(res => res.json());
  
  const setVal = (elId, val) => { const el = document.getElementById(elId); if (el) el.value = val; };
  setVal('reqTitle', r.title || '');
  // Set client dropdown
  const clientSel = document.getElementById('reqClientSel');
  if (clientSel) {
    const allOptions = clientSel.options;
    let found = false;
    for (let i = 0; i < allOptions.length; i++) {
      if (allOptions[i].value === r.client_name) {
        clientSel.value = r.client_name;
        found = true;
        break;
      }
    }
    if (!found) clientSel.value = '';
  }
  setVal('reqDegree', extractRequirementField(r.description, 'Degree'));
  setVal('reqExperience', extractRequirementField(r.description, 'Experience'));
  setVal('reqLocation', r.location || extractRequirementField(r.description, 'Location'));
  setVal('reqPrimarySkills', extractRequirementField(r.description, 'Primary Skills'));
  setVal('reqSecondarySkills', extractRequirementField(r.description, 'Secondary Skills'));
  const descriptionLines = String(r.description || '').split(/\r?\n/).filter(line => !/^(Industry|Degree|Experience|Languages|Location|Primary Skills|Secondary Skills):/i.test(line.trim()));
  setVal('reqDescription', descriptionLines.join('\n').trim());
  
  const titleEl = document.getElementById('reqModalTitle');
  if (titleEl) titleEl.textContent = 'Edit Requirement';
  
  const jdInput = document.getElementById('reqJdFile');
  if (jdInput) jdInput.value = '';
  const jdStatus = document.getElementById('reqJdStatus');
  if (jdStatus) {
    jdStatus.dataset.hasJd = r.jd_url ? '1' : '0';
    jdStatus.innerHTML = r.jd_url
      ? `Current JD: <a href="${escapeHtml(r.jd_url)}" target="_blank">${escapeHtml(r.jd_filename || 'View JD')}</a>`
      : 'No JD uploaded.';
  }
  
  window.currentEditRequirementId = id;
  document.getElementById('requirementModal').style.display = 'flex';
  document.getElementById('requirementModal').classList.add('active');
}

async function showAddRequirementModal() { 
  console.log('showAddRequirementModal called');
  try {
    const mappedClients = await getClientOptionsCached({force:true});
    populateRequirementClientSelect(mappedClients);
  } catch(e) {
    console.warn('Unable to refresh mapped clients', e);
  }
  const btn = document.getElementById('saveReqBtn');
  btn.disabled = false;
  btn.innerText = 'Save Requirement';
  const ids = ['reqTitle','reqClient'];
  ids.forEach(id => { const el = document.getElementById(id); if (el) el.value = ''; });
  const clientSel = document.getElementById('reqClientSel');
  if (clientSel) {
    clientSel.value = '';
    clientSel.style.display = '';
  }
  setValue('reqDegree', '');
  setValue('reqExperience', '');
  setValue('reqLocation', '');
  setValue('reqPrimarySkills', '');
  setValue('reqSecondarySkills', '');
  setValue('reqDescription', '');
  const jdInput = document.getElementById('reqJdFile');
  if (jdInput) jdInput.value = '';
  const jdStatus = document.getElementById('reqJdStatus');
  if (jdStatus) {
    jdStatus.dataset.hasJd = '0';
    jdStatus.textContent = 'No JD uploaded.';
  }
  const parseStatus = document.getElementById('reqJdParseStatus');
  if (parseStatus) parseStatus.textContent = 'Parse JD text or attached JD file to fill skills.';
  const saveStatus = document.getElementById('reqSaveStatus');
  if (saveStatus) saveStatus.textContent = '';
  const titleEl = document.getElementById('reqModalTitle');
  if (titleEl) titleEl.textContent = 'Add Requirement';
  const titleMenu = document.getElementById('reqTitleSuggestionMenu');
  if (titleMenu) titleMenu.classList.remove('active');
  
  // Populate team dropdowns
  populateTeamDropdowns();
  fetch('/api/requirements')
    .then(r => r.json())
    .then(rows => renderRequirementTitleSuggestions(Array.isArray(rows) ? rows : (rows.rows || [])))
    .catch(e => console.warn('Unable to load requirement title suggestions', e));
  
  document.getElementById('requirementModal').style.display = 'flex';
  document.getElementById('requirementModal').classList.add('active');
}

function formatExperienceRange(exp) {
  if (!exp || typeof exp !== 'object') return '';
  const min = exp.min_years ?? exp.min ?? '';
  const max = exp.max_years ?? exp.max ?? '';
  if (min !== '' && max !== '' && Number(min) !== Number(max)) return `${min}-${max} years`;
  if (min !== '') return `${min}+ years`;
  if (max !== '') return `Up to ${max} years`;
  return '';
}

async function parseRequirementJd() {
  const jdFile = document.getElementById('reqJdFile')?.files?.[0];
  const jdText = valueOf('reqDescription').trim();
  const btn = document.getElementById('parseReqJdBtn');
  const status = document.getElementById('reqJdParseStatus');
  if (!jdFile && !jdText) {
    showToast('Paste JD text or attach a JD file first', 'error');
    return;
  }
  const fd = new FormData();
  if (jdFile) fd.append('jd_file', jdFile);
  if (jdText) fd.append('jd_text', jdText);
  if (btn) {
    btn.disabled = true;
    btn.textContent = 'Parsing...';
  }
  if (status) status.textContent = 'Parsing JD for skills, experience, and location...';
  try {
    const res = await fetch('/api/parse_jd', {method: 'POST', body: fd});
    const data = await readJsonResponse(res);
    if (!res.ok || data.error) throw new Error(data.error || 'Unable to parse JD');
    const parsed = data.parsed_jd || data;
    const primary = parsed.must_have_skills || parsed.primary_skills || parsed.tools_technologies || [];
    const secondary = parsed.nice_to_have_skills || parsed.secondary_skills || [];
    const experience = formatExperienceRange(parsed.experience_required);
    if (primary.length) setValue('reqPrimarySkills', primary.join(', '));
    if (secondary.length) setValue('reqSecondarySkills', secondary.join(', '));
    if (experience) setValue('reqExperience', experience);
    if (parsed.location) setValue('reqLocation', parsed.location);
    if (parsed.education_required) setValue('reqDegree', Array.isArray(parsed.education_required) ? parsed.education_required.join(', ') : parsed.education_required);
    if (parsed.title && !valueOf('reqTitle').trim()) setValue('reqTitle', parsed.title);
    if (status) status.textContent = 'Parsed successfully. Review the filled fields before saving.';
    showToast('JD parsed successfully', 'success');
  } catch(e) {
    if (status) status.textContent = e.message;
    showToast(e.message, 'error');
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.textContent = 'Parse Job Description';
    }
  }
}

async function saveRequirement() {
  const btn = document.getElementById('saveReqBtn');
  const saveStatus = document.getElementById('reqSaveStatus');
  const setSaveError = (message, title='Requirement Not Saved') => {
    if (saveStatus) {
      saveStatus.style.color = '#ff8a8a';
      saveStatus.textContent = message || 'Unable to save requirement.';
    }
    showToast(message || 'Unable to save requirement', 'error');
    showAlertPopup({
      title,
      message: message || 'Unable to save requirement.',
      okText: 'OK'
    });
  };
  if (saveStatus) {
    saveStatus.style.color = '#aab3c8';
    saveStatus.textContent = '';
  }
  btn.disabled = true;
  btn.innerText = 'Saving...';

  const sel = document.getElementById('reqClientSel');
  const clientName = sel.value;

  const reqLocationValue = valueOf('reqLocation').trim();
  const body = {
    title: document.getElementById('reqTitle').value.trim(),
    client_name: clientName,
    location: reqLocationValue,
    has_jd_text: Boolean(valueOf('reqDescription').trim()),
    description: [
      valueOf('reqDescription'),
      'Degree: ' + valueOf('reqDegree'),
      'Experience: ' + valueOf('reqExperience'),
      reqLocationValue ? 'Location: ' + reqLocationValue : '',
      'Primary Skills: ' + valueOf('reqPrimarySkills'),
      'Secondary Skills: ' + valueOf('reqSecondarySkills')
    ].filter(Boolean).join('\n')
  };
  if (!body.title) {
    setSaveError('Requirement title is required');
    btn.disabled = false;
    btn.innerText = 'Save Requirement';
    return;
  }
  if (!body.client_name) {
    setSaveError('Client is required');
    btn.disabled = false;
    btn.innerText = 'Save Requirement';
    return;
  }
  if (!reqLocationValue) {
    const locationEl = document.getElementById('reqLocation');
    if (locationEl) locationEl.focus();
    setSaveError('Please enter the requirement location before saving.', 'Location Required');
    btn.disabled = false;
    btn.innerText = 'Save Requirement';
    return;
  }
  const jdFile = document.getElementById('reqJdFile')?.files?.[0];
  body.has_jd_file = Boolean(jdFile);
  const isEdit = window.currentEditRequirementId;
  const existingJd = (document.getElementById('reqJdStatus')?.dataset || {}).hasJd === '1';
  if (!valueOf('reqDescription').trim() && !jdFile && !existingJd) {
    setSaveError(
      'Please paste the job description text or upload a JD file before saving this requirement.',
      'Job Description Required'
    );
    btn.disabled = false;
    btn.innerText = 'Save Requirement';
    return;
  }

  const method = isEdit ? 'PATCH' : 'POST';
  const url = isEdit ? '/api/requirements/' + window.currentEditRequirementId : '/api/requirements';

  let res;
  let data;
  try {
    res = await fetch(url, {
      method: method,
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify(body)
    });
    data = await readJsonResponse(res);
  } catch(e) {
    setSaveError(e.message || 'Unable to save requirement. Please try again.');
    btn.disabled = false;
    btn.innerText = 'Save Requirement';
    return;
  }

  if (data.ok || data.id) {
    const reqId = data.id || window.currentEditRequirementId;
    if (jdFile) {
      const fd = new FormData();
      fd.append('file', jdFile);
      let jdRes;
      let jdData;
      try {
        jdRes = await fetch('/api/requirements/' + reqId + '/upload_jd', {method:'POST', body:fd});
        jdData = await jdRes.json().catch(() => ({}));
      } catch(e) {
        setSaveError('Requirement was saved, but JD upload failed: ' + (e.message || 'network error'), 'JD Upload Failed');
        btn.disabled = false;
        btn.innerText = 'Save Requirement';
        return;
      }
      if (!jdRes.ok || jdData.error) {
        setSaveError('Requirement was saved, but JD upload failed: ' + (jdData.error || 'Unknown upload error'), 'JD Upload Failed');
        btn.disabled = false;
        btn.innerText = 'Save Requirement';
        return;
      }
    }

    btn.innerText = 'Saved âœ“';

    setTimeout(() => {
        btn.disabled = false;
        btn.innerText = 'Save Requirement';
    }, 500);

    closeModal('requirementModal');
    loadRequirements();
    loadFilterOptions();
    showToast(isEdit ? 'Requirement updated' : 'Requirement added', 'success');
    window.currentEditRequirementId = null;
  } else {
    setSaveError(data.error || `Error saving requirement (${res.status})`);
    btn.disabled = false;
    btn.innerText = 'Save Requirement';
  }
}

async function deleteRequirement(id) {
  const ok = await confirmAction({
    title: 'Delete requirement?',
    message: 'This will delete the requirement and its screening checks. Existing candidates will remain in the system.',
    okText: 'Delete'
  });
  if (!ok) return;
  const res = await fetch('/api/requirements/' + id, {method:'DELETE'});
  const data = await res.json().catch(() => ({}));
  if (res.ok && data.ok !== false) {
    await loadRequirements();
    await loadFilterOptions();
    showToast('Requirement deleted', 'success');
  } else {
    showToast(data.error || 'Unable to delete requirement', 'error');
  }
}

function viewRequirement(id) { fetch('/api/requirements/' + id).then(r => r.json()).then(r => { document.getElementById('reqViewTitle').textContent = r.title || '-'; document.getElementById('reqViewClient').textContent = r.client_name || '-'; document.getElementById('reqViewStatus').textContent = r.status || '-'; document.getElementById('reqViewTarget').textContent = r.daily_target || '-'; document.getElementById('reqViewLocation').textContent = r.location || '-'; document.getElementById('reqViewRemote').textContent = r.remote ? 'Yes' : 'No'; document.getElementById('reqViewSubmissions').textContent = r.submissions || 0; showModal('viewRequirementModal'); }); }

function showModal(id) { document.getElementById(id).classList.add('active'); }
function closeModal(id) {
  const modal = document.getElementById(id);
  if (!modal) return;
  modal.classList.remove('active');
  if (id === 'dailyReportModal') {
    const openBtn = document.getElementById('openDailyReportBtn');
    if (openBtn) openBtn.disabled = false;
    const feedbackBtn = document.getElementById('openFeedbackRequestBtn');
    if (feedbackBtn) feedbackBtn.disabled = false;
    window.dailyReportSubmitting = false;
    setDailyReportSendState(false, window.dailyReportMode || 'report');
  }
  if (id === 'requirementModal') {
    window.currentEditRequirementId = null;
  }
}
async function logout() { await fetch('/api/logout',{method:'POST'}); localStorage.removeItem('hrguru_user'); window.location.href='/login'; }

async function loadReportData() {
  const reportType = document.getElementById('reportType').value;
  const analyticsClientSel = document.getElementById('analyticsClientFilter');
  if (analyticsClientSel) analyticsClientSel.style.display = reportType === 'daily_dashboard' ? '' : 'none';
  const client = document.getElementById('analyticsClientFilter')?.value || '';
  const fromDate = document.getElementById('reportFromDate').value;
  const toDate = document.getElementById('reportToDate').value;
  const params = new URLSearchParams();
  params.set('type', reportType);
  if (client && reportType === 'daily_dashboard') params.set('client', client);
  if (fromDate) params.set('from_date', fromDate);
  if (toDate) params.set('to_date', toDate);
  
  const container = document.getElementById('reportContent');
  container.innerHTML = '<div style="text-align:center;padding:60px;color:#6b7494">Loading...</div>';
  
  try {
    const res = await fetch('/api/reports?' + params);
    const data = await res.json();
    window.currentReportSnapshot = { reportType, fromDate, toDate, client, data: JSON.parse(JSON.stringify(data || {})) };
    
    if (reportType === 'daily_dashboard') {
      const totals = data.totals || {};
      let html = '<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:16px;margin-bottom:24px">';
      html += '<div class="stat-card"><div class="num">' + (totals.submissions || 0) + '</div><div class="label">Submissions Today</div></div>';
      html += '<div class="stat-card"><div class="num">' + (totals.recruiters || 0) + '</div><div class="label">Recruiters Active</div></div>';
      html += '<div class="stat-card"><div class="num">' + (totals.requirements || 0) + '</div><div class="label">Requirements Worked</div></div>';
      html += '</div><h3 style="margin:0 0 12px;color:#fff">Today by Recruiter and Requirement</h3>';
      if (client) {
        html += '<div style="margin:0 0 12px;color:#8b95b5;font-size:12px">Client filter: <span style="color:#fff;font-weight:600">' + escapeHtml(client) + '</span></div>';
      }
      html += '<table style="width:100%;border-collapse:collapse"><tr><th style="text-align:left;padding:8px;border-bottom:1px solid #2a2f3a;color:#8892a0">Recruiter</th><th style="text-align:left;padding:8px;border-bottom:1px solid #2a2f3a;color:#8892a0">Requirement</th><th style="text-align:right;padding:8px;border-bottom:1px solid #2a2f3a;color:#8892a0">Submissions</th></tr>';
      if (!data.rows || !data.rows.length) {
        html += '<tr><td colspan="3" style="text-align:center;padding:40px;color:#6b7494">No submissions today</td></tr>';
      }
      (data.rows || []).forEach(r => {
        html += '<tr><td style="padding:8px;border-bottom:1px solid #2a2f3a">' + (r.recruiter || '-') + '</td><td style="padding:8px;border-bottom:1px solid #2a2f3a">' + (r.requirement || '-') + '</td><td style="text-align:right;padding:8px;border-bottom:1px solid #2a2f3a">' + (r.submissions || 0) + '</td></tr>';
      });
      html += '</table>';
      container.innerHTML = html;
    } else if (reportType === 'summary') {
      let html = '<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:16px;margin-bottom:24px">';
      html += '<div class="stat-card"><div class="num" style="font-size:36px">' + (data.total || 0) + '</div><div class="label">Total Candidates</div></div>';
      html += '</div><h3 style="margin:20px 0 12px;color:#fff">By Status</h3>';
      html += '<table style="width:100%;border-collapse:collapse"><tr><th style="text-align:left;padding:8px;border-bottom:1px solid #2a2f3a;color:#8892a0">Status</th><th style="text-align:right;padding:8px;border-bottom:1px solid #2a2f3a;color:#8892a0">Count</th></tr>';
      (data.by_status || []).forEach(s => {
        html += '<tr><td style="padding:8px;border-bottom:1px solid #2a2f3a">' + (s.status || '-') + '</td><td style="text-align:right;padding:8px;border-bottom:1px solid #2a2f3a">' + (s.cnt || 0) + '</td></tr>';
      });
      html += '</table><h3 style="margin:20px 0 12px;color:#fff">Top Roles</h3>';
      html += '<table style="width:100%;border-collapse:collapse"><tr><th style="text-align:left;padding:8px;border-bottom:1px solid #2a2f3a;color:#8892a0">Role</th><th style="text-align:right;padding:8px;border-bottom:1px solid #2a2f3a;color:#8892a0">Count</th></tr>';
      (data.by_role || []).forEach(r => {
        html += '<tr><td style="padding:8px;border-bottom:1px solid #2a2f3a">' + (r.role_name || '-') + '</td><td style="text-align:right;padding:8px;border-bottom:1px solid #2a2f3a">' + (r.cnt || 0) + '</td></tr>';
      });
      html += '</table>';
      container.innerHTML = html;
    } else if (reportType === 'sourcer') {
      let html = '<h3 style="margin:0 0 12px;color:#fff">Sourcer Performance</h3>';
      html += '<table style="width:100%;border-collapse:collapse"><tr><th style="text-align:left;padding:8px;border-bottom:1px solid #2a2f3a;color:#8892a0">Sourcer</th><th style="text-align:right;padding:8px;border-bottom:1px solid #2a2f3a;color:#8892a0">Submissions</th><th style="text-align:right;padding:8px;border-bottom:1px solid #2a2f3a;color:#8892a0">Success</th></tr>';
      data.forEach(s => {
        html += '<tr><td style="padding:8px;border-bottom:1px solid #2a2f3a">' + (s.sourcer || '-') + '</td><td style="text-align:right;padding:8px;border-bottom:1px solid #2a2f3a">' + (s.submissions || 0) + '</td><td style="text-align:right;padding:8px;border-bottom:1px solid #2a2f3a">' + (s.success || 0) + '</td></tr>';
      });
      html += '</table>';
      container.innerHTML = html || '<div style="text-align:center;color:#6b7494;padding:60px">No data</div>';
    } else if (reportType === 'sourcer_today') {
      const list = Array.isArray(data && data.rows) ? data.rows : (Array.isArray(data) ? data : []);
      const totals = data && data.totals ? data.totals : {};
      const maxCount = Math.max(1, ...list.map(r => Number(r.submissions || 0)));
      let html = '<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:16px;margin-bottom:24px">';
      html += '<div class="stat-card"><div class="num">' + (totals.submissions || 0) + '</div><div class="label">Submissions Today</div></div>';
      html += '<div class="stat-card"><div class="num">' + (totals.sourcers || list.length || 0) + '</div><div class="label">Sourcers Active</div></div>';
      html += '</div><h3 style="margin:0 0 12px;color:#fff">Today Submissions</h3>';
      if (!list.length) {
        html += '<div style="text-align:center;color:#6b7494;padding:60px">No submissions today</div>';
      } else {
        html += '<div style="display:flex;flex-direction:column;gap:12px">';
        list.forEach(r => {
          const count = Number(r.submissions || 0);
          const width = Math.max(6, Math.round((count / maxCount) * 100));
          html += '<div style="background:#252a3a;border:1px solid #2f3546;border-radius:10px;padding:12px 14px">';
          html += '<div style="display:flex;justify-content:space-between;align-items:center;gap:12px;margin-bottom:8px">';
          html += '<div style="font-weight:600;color:#fff">' + (r.sourcer || '-') + '</div>';
          html += '<div style="color:#e8643a;font-weight:700">' + count + '</div>';
          html += '</div>';
          html += '<div style="height:12px;background:#1a1f2c;border-radius:999px;overflow:hidden">';
          html += '<div style="height:100%;width:' + width + '%;background:linear-gradient(90deg,#e8643a,#f2a65a)"></div>';
          html += '</div>';
          html += '</div>';
        });
        html += '</div>';
      }
      container.innerHTML = html;
    } else if (reportType === 'status') {
      let html = '<h3 style="margin:0 0 12px;color:#fff">Status Distribution</h3>';
      html += '<div style="display:flex;gap:12px;flex-wrap:wrap">';
      data.forEach(s => {
        const pct = data.reduce((a,b) => a + b.count, 0);
        html += '<div style="background:#252a3a;padding:16px 24px;border-radius:8px;min-width:120px;text-align:center"><div style="font-size:24px;font-weight:700;color:#e8643a">' + s.count + '</div><div style="font-size:13px;color:#8892a0">' + s.status + '</div></div>';
      });
      html += '</div>';
      container.innerHTML = html;
    } else if (reportType === 'skills') {
      let html = '<h3 style="margin:0 0 12px;color:#fff">Top Skills</h3>';
      html += '<div style="display:flex;gap:8px;flex-wrap:wrap">';
      data.forEach(s => {
        html += '<span style="background:#252a3a;padding:6px 12px;border-radius:16px;font-size:13px">' + s.skill + ' <span style="color:#e8643a">' + s.count + '</span></span>';
      });
      html += '</div>';
      container.innerHTML = html || '<div style="text-align:center;color:#6b7494;padding:60px">No data</div>';
    } else if (reportType === 'submissions') {
      let html = '<h3 style="margin:0 0 12px;color:#fff">Daily Submissions</h3>';
      html += '<table style="width:100%;border-collapse:collapse"><tr><th style="text-align:left;padding:8px;border-bottom:1px solid #2a2f3a;color:#8892a0">Date</th><th style="text-align:right;padding:8px;border-bottom:1px solid #2a2f3a;color:#8892a0">Submissions</th></tr>';
      data.forEach(d => {
        html += '<tr><td style="padding:8px;border-bottom:1px solid #2a2f3a">' + d.date + '</td><td style="text-align:right;padding:8px;border-bottom:1px solid #2a2f3a">' + d.count + '</td></tr>';
      });
      html += '</table>';
      container.innerHTML = html || '<div style="text-align:center;color:#6b7494;padding:60px">No data</div>';
    } else if (reportType === 'no_submission_today') {
      const list = Array.isArray(data) ? data : [];
      let html = '<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:16px;margin-bottom:24px">';
      html += '<div class="stat-card"><div class="num">' + list.length + '</div><div class="label">Recruiters Pending</div></div>';
      html += '</div><h3 style="margin:0 0 12px;color:#fff">Recruiters who have not submitted today</h3>';
      html += '<table style="width:100%;border-collapse:collapse"><tr><th style="text-align:left;padding:8px;border-bottom:1px solid #2a2f3a;color:#8892a0">Name</th><th style="text-align:left;padding:8px;border-bottom:1px solid #2a2f3a;color:#8892a0">Email</th></tr>';
      if (!list.length) {
        html += '<tr><td colspan="2" style="text-align:center;padding:40px;color:#6b7494">All recruiters have submitted today</td></tr>';
      }
      list.forEach(r => {
        html += '<tr><td style="padding:8px;border-bottom:1px solid #2a2f3a">' + (r.name || '-') + '</td><td style="padding:8px;border-bottom:1px solid #2a2f3a">' + (r.email || '-') + '</td></tr>';
      });
      html += '</table>';
      container.innerHTML = html;
    }
  } catch(e) {
    container.innerHTML = '<div style="text-align:center;color:#e86a6a;padding:60px">Error: ' + e.message + '</div>';
  }
}

function escapeCsvValue(value) {
  const text = String(value ?? '');
  if (/[",\n\r]/.test(text)) return '"' + text.replace(/"/g, '""') + '"';
  return text;
}

function downloadCsv(filename, rows) {
  const csv = rows.map(row => row.map(escapeCsvValue).join(',')).join('\r\n');
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

function exportRowsToCsv(rows, columns, sectionTitle) {
  const csvRows = [];
  if (sectionTitle) csvRows.push([sectionTitle]);
  csvRows.push(columns);
  (rows || []).forEach(row => {
    csvRows.push(columns.map(col => row[col] ?? row[col.toLowerCase()] ?? row[col.replace(/\s+/g, '_').toLowerCase()] ?? ''));
  });
  csvRows.push([]);
  return csvRows;
}

function exportReport() {
  const snapshot = window.currentReportSnapshot || {};
  const reportType = snapshot.reportType || document.getElementById('reportType').value;
  const data = snapshot.data || {};
  const stamp = new Date().toISOString().slice(0,10);

  if (reportType === 'daily_dashboard') {
    const rows = [];
    rows.push([`Daily Dashboard Report`, `Date`, snapshot.fromDate || '', snapshot.toDate || '']);
    rows.push(['Client', snapshot.client || 'All Clients']);
    rows.push([]);
    rows.push(['Summary']);
    rows.push(['Metric', 'Value']);
    const totals = data.totals || {};
    rows.push(['Submissions Today', totals.submissions || 0]);
    rows.push(['Recruiters Active', totals.recruiters || 0]);
    rows.push(['Requirements Worked', totals.requirements || 0]);
    rows.push([]);
    rows.push(['Today by Recruiter and Requirement']);
    rows.push(['Recruiter', 'Requirement', 'Submissions']);
    (data.rows || []).forEach(r => rows.push([r.recruiter || '-', r.requirement || '-', r.submissions || 0]));
    downloadCsv(`report_daily_dashboard_${stamp}.csv`, rows);
    return;
  }

  if (reportType === 'summary') {
    const rows = [];
    rows.push(['Summary Report', 'Date', snapshot.fromDate || '', snapshot.toDate || '']);
    rows.push([]);
    rows.push(['By Status']);
    rows.push(['Status', 'Count']);
    (data.by_status || []).forEach(s => rows.push([s.status || '-', s.cnt || 0]));
    rows.push([]);
    rows.push(['Top Roles']);
    rows.push(['Role', 'Count']);
    (data.by_role || []).forEach(r => rows.push([r.role_name || '-', r.cnt || 0]));
    downloadCsv(`report_summary_${stamp}.csv`, rows);
    return;
  }

  if (reportType === 'sourcer') {
    const rows = [['Sourcer Performance Report'], ['Sourcer', 'Submissions', 'Success']];
    (Array.isArray(data) ? data : []).forEach(s => rows.push([s.sourcer || '-', s.submissions || 0, s.success || 0]));
    downloadCsv(`report_sourcer_${stamp}.csv`, rows);
    return;
  }

  if (reportType === 'sourcer_today') {
    const rows = [['Today Submissions'], ['Sourcer', 'Submissions']];
    const list = Array.isArray(data && data.rows) ? data.rows : (Array.isArray(data) ? data : []);
    (list || []).forEach(s => rows.push([s.sourcer || '-', s.submissions || 0]));
    downloadCsv(`report_sourcer_today_${stamp}.csv`, rows);
    return;
  }

  if (reportType === 'status') {
    const rows = [['Status Distribution Report'], ['Status', 'Count']];
    (Array.isArray(data) ? data : []).forEach(s => rows.push([s.status || '-', s.count || 0]));
    downloadCsv(`report_status_${stamp}.csv`, rows);
    return;
  }

  if (reportType === 'skills') {
    const rows = [['Top Skills Report'], ['Skill', 'Count']];
    (Array.isArray(data) ? data : []).forEach(s => rows.push([s.skill || '-', s.count || 0]));
    downloadCsv(`report_skills_${stamp}.csv`, rows);
    return;
  }

  if (reportType === 'submissions') {
    const rows = [['Daily Submissions Report'], ['Date', 'Submissions']];
    (Array.isArray(data) ? data : []).forEach(d => rows.push([d.date || '-', d.count || 0]));
    downloadCsv(`report_submissions_${stamp}.csv`, rows);
    return;
  }

  if (reportType === 'no_submission_today') {
    const rows = [['Recruiters Pending Submission'], ['Name', 'Email']];
    (Array.isArray(data) ? data : []).forEach(r => rows.push([r.name || '-', r.email || '-']));
    downloadCsv(`report_no_submission_today_${stamp}.csv`, rows);
    return;
  }

  if (reportType === 'status_detail') {
    const statusLabel = (snapshot.status || document.querySelector('.reporting-status-pill.active')?.textContent || 'status').replace(/[^A-Za-z0-9_-]+/g, '_');
    const rows = [['Status Detail Report'], ['Role', 'Recruiter', 'Count']];
    (Array.isArray(data) ? data : []).forEach(r => rows.push([r.role_name || '-', r.recruiter_name || '-', r.cnt || 0]));
    downloadCsv(`report_status_detail_${statusLabel}_${stamp}.csv`, rows);
    return;
  }

  showToast('Nothing to export for this report type yet.', 'error');
}

async function exportReportExcel() {
  const snapshot = window.currentReportSnapshot || {};
  const reportType = snapshot.reportType || document.getElementById('reportType').value;
  if (reportType !== 'daily_dashboard') {
    showToast('Excel export is available for Today by Recruiter only.', 'error');
    return;
  }
  try {
    const params = new URLSearchParams();
    params.set('type', reportType);
    if (snapshot.client) params.set('client', snapshot.client);
    const res = await fetch('/api/reports/export?' + params);
    if (!res.ok) {
      const payload = await res.json().catch(() => ({}));
      throw new Error(payload.error || 'Unable to export Excel file.');
    }
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    const dateStamp = new Date().toISOString().slice(0,10);
    const clientPart = snapshot.client ? '_' + String(snapshot.client).replace(/[^A-Za-z0-9_-]+/g, '_').slice(0,40) : '';
    a.download = `report_daily_dashboard${clientPart}_${dateStamp}.xlsx`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  } catch (err) {
    showToast(err.message || 'Unable to export Excel file.', 'error');
  }
}

function exportAnalyticsData() {
  const snapshot = window.currentReportSnapshot || {};
  const reportType = snapshot.reportType || document.getElementById('reportType').value;
  if (reportType === 'daily_dashboard') {
    exportReportExcel();
    return;
  }
  exportReport();
}

function setReportPeriod(period) {
  const today = new Date();
  let fromDate = '', toDate = today.toISOString().split('T')[0];
  if (period === 'today') {
    fromDate = toDate;
  } else if (period === 'week') {
    const day = today.getDay();
    const diff = today.getDate() - day + (day === 0 ? -6 : 1);
    fromDate = new Date(today.setDate(diff)).toISOString().split('T')[0];
  } else if (period === 'month') {
    fromDate = today.toISOString().split('T')[0].substring(0, 7) + '-01';
  }
  document.getElementById('reportFromDate').value = fromDate;
  document.getElementById('reportToDate').value = toDate;
  loadReportData();
}

async function loadNoSubmissionTodayReport() {
  const container = document.getElementById('reportContent');
  if (container) container.innerHTML = '<div style="text-align:center;padding:60px;color:#6b7494">Loading...</div>';
  try {
    const res = await fetch('/api/reporting/no_submission_today');
    const data = await res.json();
    window.currentReportSnapshot = {
      reportType: 'no_submission_today',
      fromDate: '',
      toDate: '',
      data: JSON.parse(JSON.stringify(data || []))
    };
    const list = Array.isArray(data) ? data : [];
    let html = '<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:16px;margin-bottom:24px">';
    html += '<div class="stat-card"><div class="num">' + list.length + '</div><div class="label">Recruiters Pending</div></div>';
    html += '</div><h3 style="margin:0 0 12px;color:#fff">Recruiters who have not submitted today</h3>';
    html += '<table style="width:100%;border-collapse:collapse"><tr><th style="text-align:left;padding:8px;border-bottom:1px solid #2a2f3a;color:#8892a0">Name</th><th style="text-align:left;padding:8px;border-bottom:1px solid #2a2f3a;color:#8892a0">Email</th></tr>';
    if (!list.length) {
      html += '<tr><td colspan="2" style="text-align:center;padding:40px;color:#6b7494">All recruiters have submitted today</td></tr>';
    }
    list.forEach(r => {
      html += '<tr><td style="padding:8px;border-bottom:1px solid #2a2f3a">' + (r.name || '-') + '</td><td style="padding:8px;border-bottom:1px solid #2a2f3a">' + (r.email || '-') + '</td></tr>';
    });
    html += '</table>';
    if (container) container.innerHTML = html;
  } catch(e) {
    if (container) container.innerHTML = '<div style="text-align:center;color:#e86a6a;padding:60px">Error: ' + e.message + '</div>';
  }
}

async function loadSourcerSubmissionTodayReport() {
  const container = document.getElementById('reportContent');
  if (container) container.innerHTML = '<div style="text-align:center;padding:60px;color:#6b7494">Loading...</div>';
  try {
    const res = await fetch('/api/reports?type=sourcer_today');
    const data = await res.json();
    window.currentReportSnapshot = {
      reportType: 'sourcer_today',
      fromDate: '',
      toDate: '',
      data: JSON.parse(JSON.stringify(data || {}))
    };
    const list = Array.isArray(data && data.rows) ? data.rows : (Array.isArray(data) ? data : []);
    const totals = data && data.totals ? data.totals : {};
    const maxCount = Math.max(1, ...list.map(r => Number(r.submissions || 0)));
    let html = '<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:16px;margin-bottom:24px">';
    html += '<div class="stat-card"><div class="num">' + (totals.submissions || 0) + '</div><div class="label">Submissions Today</div></div>';
    html += '<div class="stat-card"><div class="num">' + (totals.sourcers || list.length || 0) + '</div><div class="label">Sourcers Active</div></div>';
    html += '</div><h3 style="margin:0 0 12px;color:#fff">Today Submissions</h3>';
    if (!list.length) {
      html += '<div style="text-align:center;color:#6b7494;padding:60px">No submissions today</div>';
    } else {
      html += '<div style="display:flex;flex-direction:column;gap:12px">';
      list.forEach(r => {
        const count = Number(r.submissions || 0);
        const width = Math.max(6, Math.round((count / maxCount) * 100));
        html += '<div style="background:#252a3a;border:1px solid #2f3546;border-radius:10px;padding:12px 14px">';
        html += '<div style="display:flex;justify-content:space-between;align-items:center;gap:12px;margin-bottom:8px">';
        html += '<div style="font-weight:600;color:#fff">' + (r.sourcer || '-') + '</div>';
        html += '<div style="color:#e8643a;font-weight:700">' + count + '</div>';
        html += '</div>';
        html += '<div style="height:12px;background:#1a1f2c;border-radius:999px;overflow:hidden">';
        html += '<div style="height:100%;width:' + width + '%;background:linear-gradient(90deg,#e8643a,#f2a65a)"></div>';
        html += '</div>';
        html += '</div>';
      });
      html += '</div>';
    }
    if (container) container.innerHTML = html;
  } catch(e) {
    if (container) container.innerHTML = '<div style="text-align:center;color:#e86a6a;padding:60px">Error: ' + e.message + '</div>';
  }
}

async function loadStatusReport(status) {
  const fromDate = document.getElementById('reportFromDate').value;
  const toDate = document.getElementById('reportToDate').value;
  const container = document.getElementById('reportContent');
  container.innerHTML = '<div style="text-align:center;padding:60px;color:#6b7494">Loading...</div>';
  
  const params = new URLSearchParams();
  params.set('status', status);
  if (fromDate) params.set('from_date', fromDate);
  if (toDate) params.set('to_date', toDate);
  
  try {
    const res = await fetch('/api/reports?type=status_detail&' + params);
    const data = await res.json();
    window.currentReportSnapshot = {
      reportType: 'status_detail',
      fromDate,
      toDate,
      status,
      data: JSON.parse(JSON.stringify(data || []))
    };
    
    let html = '<h3 style="margin:0 0 16px;color:#fff">' + status + ' - Role & Recruiter Breakdown</h3>';
    html += '<table style="width:100%;border-collapse:collapse"><tr><th style="text-align:left;padding:8px;border-bottom:1px solid #2a2f3a;color:#8892a0">Role</th><th style="text-align:left;padding:8px;border-bottom:1px solid #2a2f3a;color:#8892a0">Recruiter</th><th style="text-align:right;padding:8px;border-bottom:1px solid #2a2f3a;color:#8892a0">Count</th></tr>';
    if (data.length === 0) {
      html += '<tr><td colspan="3" style="text-align:center;padding:40px;color:#6b7494">No data found</td></tr>';
    }
    data.forEach(r => {
      html += '<tr><td style="padding:8px;border-bottom:1px solid #2a2f3a">' + (r.role_name || '-') + '</td><td style="padding:8px;border-bottom:1px solid #2a2f3a">' + (r.recruiter_name || '-') + '</td><td style="text-align:right;padding:8px;border-bottom:1px solid #2a2f3a">' + r.cnt + '</td></tr>';
    });
    html += '</table>';
    container.innerHTML = html;
  } catch(e) {
    container.innerHTML = '<div style="text-align:center;color:#e86a6a;padding:60px">Error: ' + e.message + '</div>';
  }
}

function updateSkillsHidden() {
  const sel = document.getElementById('acSkillsSel');
  const hidden = document.getElementById('acSkills');
  if (!sel || !hidden || !sel.selectedOptions) return;
  const selected = Array.from(sel.selectedOptions).map(o => o.value).join(', ');
  hidden.value = selected;
}

function clearAddCandidateValidation() {
  document.querySelectorAll('#addCandidateModal .form-group.invalid').forEach(group => group.classList.remove('invalid'));
  document.querySelectorAll('#addCandidateModal .field-error').forEach(err => err.remove());
  const alertBox = document.getElementById('addCandidateAlert');
  if (alertBox) {
    alertBox.style.display = 'none';
    alertBox.textContent = '';
  }
}

function markCandidateFieldInvalid(id, message) {
  const el = document.getElementById(id);
  if (!el) return null;
  const group = el.closest('.form-group');
  if (!group) return el;
  group.classList.add('invalid');
  let err = group.querySelector('.field-error');
  if (!err) {
    err = document.createElement('div');
    err.className = 'field-error';
    group.appendChild(err);
  }
  err.textContent = message;
  return el;
}

function showAddCandidateError(message, fieldId) {
  const alertBox = document.getElementById('addCandidateAlert');
  if (alertBox) {
    alertBox.textContent = message;
    alertBox.style.display = 'block';
  }
  const target = fieldId ? markCandidateFieldInvalid(fieldId, message) : alertBox;
  if (target) target.scrollIntoView({behavior:'smooth', block:'center'});
}

function validateAddCandidateForm() {
  clearAddCandidateValidation();
  const requiredFields = [
    ['acCandidateName', 'Candidate name is required'],
    ['acEmail', 'Email is required'],
    ['acPhone', 'Phone is required'],
    ['acCurrentLocation', 'Current location is required'],
    ['acPreferredLocation', 'Preferred location is required'],
    ['acNotice', 'Notice period is required'],
    ['acExperience', 'Experience is required'],
    ['acSkillsSel', 'Skills are required'],
    ['acCurrentSalary', 'Current salary is required'],
    ['acExpectedSalary', 'Expected salary is required']
  ];
  const missing = [];
  let firstInvalid = null;
  if (!valueOf('acRequirement').trim()) {
    const el = markCandidateFieldInvalid('acRequirementSearch', 'Select a requirement from the search results');
    if (!firstInvalid) firstInvalid = el;
    missing.push('Requirement is required');
  }
  requiredFields.forEach(([id, message]) => {
    if (!valueOf(id).trim()) {
      const el = markCandidateFieldInvalid(id, message);
      if (!firstInvalid) firstInvalid = el;
      missing.push(message);
    }
  });
  const cvFile = document.getElementById('acCvFile').files[0];
  if (!cvFile) {
    const el = markCandidateFieldInvalid('acCvFile', 'CV/Resume is required');
    if (!firstInvalid) firstInvalid = el;
    missing.push('CV/Resume is required');
  }
  if (missing.length) {
    if (missing.includes('CV/Resume is required')) showCandidateFormSection('personal');
    else if (missing.some(m => ['Experience is required','Skills are required','Current salary is required','Expected salary is required'].includes(m))) showCandidateFormSection('work');
    else showCandidateFormSection('personal');
    showAddCandidateError('Please complete the mandatory fields marked with *. Other candidate details can be added later.');
    if (firstInvalid) firstInvalid.scrollIntoView({behavior:'smooth', block:'center'});
    return false;
  }
  return true;
}

let currentRequirementChecks = [];
function legacyShowAddCandidateModal() {
  openAtsApplicantForm('manual');
  return;
  loadRecruiters();
  ['acCandidateName','acEmail','acPhone','acCurrentCompany','acCurrentRoleTxt','acExperience','acSkills','acSkillsSel','acNotice','acCurrentSalary','acExpectedSalary','acCurrentLocation','acPreferredLocation','acRemarks'].forEach(id => { const el = document.getElementById(id); if (el) el.value = ''; });
  const cvInput = document.getElementById('acCvFile');
  if (cvInput) cvInput.value = '';
  const parseStatus = document.getElementById('parseStatus');
  if (parseStatus) parseStatus.textContent = '';
  const parseBtn = document.getElementById('parseCvBtn');
  if (parseBtn) { parseBtn.disabled = false; parseBtn.textContent = 'Parse'; }
  clearAddCandidateValidation();
  document.getElementById('acCurrentRoleTxt').style.display = '';
  document.getElementById('acCurrentRoleSel').value = '';
  document.getElementById('acDomainSel').value = '';
  currentRequirementChecks = [];
  
  // Load requirements for dropdown
  fetch('/api/requirements').then(r => r.json()).then(reqs => {
    allRequirementOptions = reqs.filter(r => r.status === 'Open' || r.status === 'In Progress');
    const search = document.getElementById('acRequirementSearch');
    if (search) search.value = '';
    renderRequirementOptions('acRequirement', allRequirementOptions);
  });
  // Load roles for dropdown
  fetch('/api/roles').then(r => r.json()).then(data => {
    const domainSel = document.getElementById('acDomainSel');
    const roleSel = document.getElementById('acCurrentRoleSel');
    if (domainSel) {
      domainSel.innerHTML = '<option value="">Select Domain</option>';
      Object.keys(data.grouped).forEach(d => { domainSel.innerHTML += '<option value="'+d+'">'+d+'</option>'; });
      domainSel.innerHTML += '<option value="__custom__">+ Custom Role</option>';
    }
    if (roleSel) {
      roleSel.innerHTML = '<option value="">Select Role</option>';
    }
    domainSel.onchange = function() {
      const domain = this.value;
      fetch('/api/roles').then(r => r.json()).then(data => {
        const roleSel = document.getElementById('acCurrentRoleSel');
        roleSel.innerHTML = '<option value="">Select Role</option>';
        if (domain === '__custom__') {
          document.getElementById('acCurrentRoleTxt').style.display = 'block';
        } else if (data.grouped[domain]) {
          data.grouped[domain].forEach(r => { roleSel.innerHTML += '<option value="'+r+'">'+r+'</option>'; });
          document.getElementById('acCurrentRoleTxt').style.display = 'none';
        }
      });
    };
  });
  
  // Reset source dropdown
  const sourceSel = document.getElementById('acSource');
  if (sourceSel) sourceSel.value = '';
  
  showModal('addCandidateModal');
}

async function loadRequirementChecks() {
  currentRequirementChecks = [];
}

async function parseCV() {
  const cvFile = document.getElementById('acCvFile').files[0];
  if (!cvFile) {
    showAddCandidateError('Choose a CV before parsing.', 'acCvFile');
    return null;
  }

  const formData = new FormData();
  formData.append('file', cvFile);
  const btn = document.getElementById('parseCvBtn');
  const status = document.getElementById('parseStatus');
  btn.disabled = true;
  btn.textContent = 'Parsing...';
  status.textContent = 'Parsing CV...';

  try {
    const res = await fetch('/api/upload_cv', {
      method: 'POST',
      body: formData
    });

    const data = await res.json();
    console.log("Upload response:", data);

    if (data.ok) {
      cvParsedData = {
        filename: data.filename,
        url: data.url,
        public_id: data.public_id,
        parsed: data.parsed || {}
      };
      applyParsedCandidateData(cvParsedData.parsed);

      if (cvParsedData.parsed && cvParsedData.parsed._parse_warning) {
        status.innerHTML =
          `<span style="color:#e8c53a">${cvParsedData.parsed._parse_warning}</span><br><a href="${data.url}" target="_blank">${data.filename}</a>`;
      } else {
        status.innerHTML =
          `Parsed: <a href="${data.url}" target="_blank">${data.filename}</a>`;
      }

      return cvParsedData;
    } else {
      status.textContent = data.error || 'Parsing failed';
    }
  } catch (e) {
    console.error("Upload failed:", e);
    status.textContent = 'Error: ' + e.message;
  } finally {
    btn.disabled = false;
    btn.textContent = 'Parse';
  }

  return null;
}

function applyParsedCandidateData(parsed) {
  if (!parsed) return;
  const map = {
    candidate_name: 'acCandidateName',
    email_addr: 'acEmail',
    phone: 'acPhone',
    current_company: 'acCurrentCompany',
    current_role: 'acCurrentRoleTxt',
    experience_years: 'acExperience',
    key_skills: 'acSkillsSel',
    notice_period: 'acNotice',
    current_salary: 'acCurrentSalary',
    expected_salary: 'acExpectedSalary',
    current_location: 'acCurrentLocation'
  };
  Object.keys(map).forEach(key => {
    const el = document.getElementById(map[key]);
    if (el && parsed[key]) el.value = String(parsed[key]).replace(/^\+91/, '');
  });
  clearAddCandidateValidation();
  showCandidateFormSection('personal');
}

async function parseCV_old() {
  const cvFile = document.getElementById('acCvFile').files[0];

  
  if (!cvFile) { alert('Select a file'); return; }
  const btn = document.getElementById('parseCvBtn');
  const status = document.getElementById('parseStatus');
  btn.disabled = true; btn.textContent = 'Parsing...';
  const formData = new FormData();
  formData.append('file', cvFile);
  try {
    const res = await fetch('/api/upload_cv', {method:'POST', body:formData});
    if (!res.ok) { throw new Error('Upload failed: ' + res.status); }
    const data = await res.json();
    if (data.ok) {
      cvParsedData = data;
      ['acCandidateName','acEmail','acPhone','acCurrentCompany','acCurrentRole','acExperience','acSkills','acNotice','acCurrentSalary','acExpectedSalary','acCurrentLocation'].forEach(id => { const v = data.parsed ? (data.parsed[id.replace('ac','').toLowerCase()] || data.parsed[id.replace('ac','')]) : null; if (v) document.getElementById(id).value = v; });
      status.textContent = 'Parsed: ' + (data.parsed?.candidate_name || cvFile.name);
    } else { status.textContent = 'Error: ' + (data.error || 'Failed'); }
  } catch(e) { status.textContent = 'Error: ' + e.message; }
  finally { btn.disabled = false; btn.textContent = 'Parse CV'; }
}

async function saveSingleCandidate() {
  const btn = document.getElementById('submitCandidateBtn');
  if (!validateAddCandidateForm()) {
    btn.disabled = false;
    btn.innerText = 'Submit Candidate';
    return;
  }
  btn.disabled = true;
  btn.innerText = 'Saving...';
  const candidateName = document.getElementById('acCandidateName').value.trim();
  const phone = document.getElementById('acPhone').value.trim();
  const email = document.getElementById('acEmail').value.trim();
  const cvFile = document.getElementById('acCvFile').files[0];

  if (cvFile && !cvParsedData) {
  console.log("Uploading CV from Add Candidate modal...");
  await parseCV();
  console.log("cvParsedData after upload:", cvParsedData);
	  console.log("cvParsedData after parse:", cvParsedData);
	}

  let cvFilename = cvFile ? cvFile.name : '';
  
  let cvUrl = '';
  let cvPublicId = '';

  if (cvParsedData) {
    cvFilename = cvParsedData.filename || cvFilename;
    cvUrl = cvParsedData.url || '';
    cvPublicId = cvParsedData.public_id || '';

  } 
  const domainSel = document.getElementById('acDomainSel')?.value || '';
  const roleSel = document.getElementById('acCurrentRoleSel')?.value || '';
  const roleTxt = document.getElementById('acCurrentRoleTxt')?.value || '';
  const currentRole = domainSel === '__custom__' ? roleTxt : (roleSel || roleTxt || '');
  
  
  const body = {
    candidate_name: candidateName, 
    email_addr: email, 
    phone: phone, 
    current_company: document.getElementById('acCurrentCompany').value, 
    current_role: currentRole, 
    experience_years: document.getElementById('acExperience').value, 
    key_skills: document.getElementById('acSkillsSel')?.value || '',
    notice_period: document.getElementById('acNotice').value, 
    current_salary: document.getElementById('acCurrentSalary').value, 
    expected_salary: document.getElementById('acExpectedSalary').value, 
    current_location: document.getElementById('acCurrentLocation').value, 
    preferred_location: document.getElementById('acPreferredLocation').value, 
    remarks: document.getElementById('acRemarks').value, 
    source: document.getElementById('acSource').value,
    sourcer_id: currentUser.team_member_id,
    cv_filename: cvFilename, 
    cv_url: cvUrl, 
    cv_public_id: cvPublicId, 
    cv_summary: cvParsedData?.parsed?.cv_summary || ''
    };
    
    console.log(body.sourcer_id);
  const reqId = document.getElementById('acRequirement').value;
  if (reqId) {
    body.requirement_id = parseInt(reqId);
  } 
  const res = await fetch('/api/candidate', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)});
  const data = await res.json();
  if (data.ok) {
    if (reqId && data.id) { await fetch('/api/submissions', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({candidate_id: data.id, requirement_id: parseInt(reqId), sourcer_id: currentUser.team_member_id, notes: document.getElementById('acRemarks').value, checks: body.checks || []})}); }
    closeModal('addCandidateModal');
    openAtsWorkspacePage('atsDashboard', 'sourcing');
    loadStats();
    btn.innerText = 'Saved âœ“';
    setTimeout(() => {
    btn.disabled = false;
    btn.innerText = 'Submit Candidate';
  }, 1000);
    cvParsedData = null;
  } else {
  showAddCandidateError(data.error || 'Failed to save candidate.');
  btn.disabled = false;
  btn.innerText = 'Submit Candidate';
  }
}
function updateStatus(id, status, select) {
  const el = select || (event && event.target ? event.target : null);
  const previousStatus = el ? (el.dataset.currentStatus || el.value || 'New') : 'New';
  if (!status || status === previousStatus) {
    if (el) applyStatusClass(el);
    return;
  }
  pendingStatusChange = {id, status, previousStatus, select: el};
  const label = document.getElementById('statusFeedbackLabel');
  if (label) label.textContent = `Feedback comments for status change to "${status}"`;
  const input = document.getElementById('statusFeedbackText');
  if (input) input.value = '';
  const alertBox = document.getElementById('statusFeedbackAlert');
  if (alertBox) {
    alertBox.style.display = 'none';
    alertBox.textContent = '';
  }
  document.getElementById('statusFeedbackModal').classList.add('active');
  setTimeout(() => input && input.focus(), 50);
}

function cancelStatusFeedback() {
  if (pendingStatusChange && pendingStatusChange.select) {
    pendingStatusChange.select.value = pendingStatusChange.previousStatus;
    applyStatusClass(pendingStatusChange.select);
  }
  pendingStatusChange = null;
  document.getElementById('statusFeedbackModal').classList.remove('active');
}

async function submitStatusFeedback() {
  if (!pendingStatusChange) return;
  const feedback = (document.getElementById('statusFeedbackText')?.value || '').trim();
  const alertBox = document.getElementById('statusFeedbackAlert');
  if (!feedback) {
    if (alertBox) {
      alertBox.textContent = 'Please enter feedback comments for this status change.';
      alertBox.style.display = 'block';
    }
    return;
  }
  try {
    const res = await fetch('/api/candidate/' + pendingStatusChange.id, {
      method:'PATCH',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({status: pendingStatusChange.status, candidate_feedback: feedback})
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok || data.error) throw new Error(data.error || 'Unable to update status');
    if (pendingStatusChange.select) {
      pendingStatusChange.select.dataset.currentStatus = pendingStatusChange.status;
      pendingStatusChange.select.value = pendingStatusChange.status;
      applyStatusClass(pendingStatusChange.select);
    }
    document.getElementById('statusFeedbackModal').classList.remove('active');
    pendingStatusChange = null;
    loadCandidateStats();
    loadDashboardCandidateList();
    showToast('Candidate status updated', 'success');
  } catch(e) {
    if (alertBox) {
      alertBox.textContent = e.message;
      alertBox.style.display = 'block';
    }
  }
}

async function loadCandidateForCommunication(id, force=false) {
  if (!force && window.currentCandidate && String(window.currentCandidate.id) === String(id)) return window.currentCandidate;
  const res = await fetch('/api/candidate/' + id);
  if (!res.ok) throw new Error('Unable to load candidate');
  window.currentCandidateId = id;
  window.currentCandidate = await res.json();
  return window.currentCandidate;
}

async function openCandidateEmail(id) {
  try {
    await loadCandidateForCommunication(id, true);
    openEmailModal();
  } catch(e) {
    alert(e.message);
  }
}

async function openCandidateWhatsApp(id) {
  try {
    const c = await loadCandidateForCommunication(id);
    const phone = c.phone || '';
    if (phone) window.open('https://wa.me/' + phone.replace(/\D/g,''));
    else alert('No phone number');
  } catch(e) {
    alert(e.message);
  }
}

function shareCandidateWhatsApp() { const c = window.currentCandidate || {}; const phone = c.phone || document.getElementById('detailPhone').textContent; if (phone && phone !== '-') { window.open('https://wa.me/' + phone.replace(/\D/g,'')); } else { alert('No phone number'); } }
function shareCandidateEmail() { 
    const email = document.getElementById('detailEmail').textContent; 
    if (email && email !== '-') { 
        openEmailModal();
    } else { 
        alert('No email'); 
    } 
}


