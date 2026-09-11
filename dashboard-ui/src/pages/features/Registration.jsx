import { useEffect, useState, useCallback } from 'react';
import { useParams } from 'react-router-dom';
import api from '../../api';
import { Select, MultiSelect } from '../../components/Select';

const FIELD_TYPES = [
  { value: 'short_text', label: 'Short Text (Single Line)' },
  { value: 'paragraph', label: 'Paragraph (Multi-line Text)' },
  { value: 'number', label: 'Number (Numeric Input)' },
  { value: 'yes_no', label: 'Yes / No (Boolean Choice)' },
  { value: 'single_select', label: 'Single Choice (Dropdown)' },
  { value: 'multiple_select', label: 'Multiple Choice (Dropdown)' },
  { value: 'user_select', label: 'Discord User Selector' },
  { value: 'role_select', label: 'Discord Role Selector' },
  { value: 'channel_select', label: 'Discord Channel Selector' },
  { value: 'date', label: 'Date (YYYY-MM-DD)' },
  { value: 'url', label: 'Website / Portfolio URL' },
];

function Registration() {
  const { guildId } = useParams();
  const [activeTab, setActiveTab] = useState('forms'); // 'forms' | 'submissions' | 'logs'
  const [forms, setForms] = useState([]);
  const [channels, setChannels] = useState([]);
  const [roles, setRoles] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  // Form creation / editing
  const [showFormModal, setShowFormModal] = useState(false);
  const [editingForm, setEditingForm] = useState(null);
  const [formData, setFormData] = useState({
    name: '',
    description: '',
    button_label: 'Register',
    button_emoji: '📝',
    button_style: 'primary',
    channel_id: '',
    enabled: true,
    approval_mode: 'automatic',
    review_channel_id: '',
    log_channel_id: '',
    auto_role_enabled: false,
    add_role_ids: [],
    remove_role_enabled: false,
    remove_role_ids: [],
    change_nickname_enabled: false,
    nickname_question_id: null,
    nickname_format: '{name}',
    single_submission: true,
    success_message: 'Your registration has been submitted successfully!',
  });

  // Question builder
  const [selectedFormForQuestions, setSelectedFormForQuestions] = useState(null);
  const [questions, setQuestions] = useState([]);
  const [showQuestionModal, setShowQuestionModal] = useState(false);
  const [editingQuestion, setEditingQuestion] = useState(null);
  const [questionFormData, setQuestionFormData] = useState({
    question: '',
    field_type: 'short_text',
    required: true,
    placeholder: '',
    options: '',
    min_length: '',
    max_length: '',
    min_value: '',
    max_value: '',
  });

  // Publish panel modal
  const [publishModalForm, setPublishModalForm] = useState(null);
  const [publishChannelId, setPublishChannelId] = useState('');
  const [publishing, setPublishing] = useState(false);

  // Submissions
  const [selectedFormForSubmissions, setSelectedFormForSubmissions] = useState(null);
  const [submissions, setSubmissions] = useState([]);
  const [submissionFilter, setSubmissionFilter] = useState('all');
  const [viewingSubmission, setViewingSubmission] = useState(null);
  const [rejectionReason, setRejectionReason] = useState('');
  const [rejectingSubId, setRejectingSubId] = useState(null);

  // Audit Logs
  const [logs, setLogs] = useState([]);

  const fetchData = useCallback(async () => {
    try {
      const [formsRes, channelsRes, rolesRes] = await Promise.allSettled([
        api.get(`/guilds/${guildId}/registration`),
        api.get(`/guilds/${guildId}/channels`),
        api.get(`/guilds/${guildId}/roles`),
      ]);

      if (formsRes.status === 'fulfilled') {
        setForms(formsRes.value.data.forms || []);
      }
      if (channelsRes.status === 'fulfilled') {
        setChannels(channelsRes.value.data.channels || []);
      }
      if (rolesRes.status === 'fulfilled') {
        setRoles(rolesRes.value.data.roles || []);
      }
      setError('');
    } catch (err) {
      setError('Failed to load registration data.');
    }
    setLoading(false);
  }, [guildId]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  // Load Submissions
  const loadSubmissions = async (formId) => {
    try {
      const url = submissionFilter !== 'all'
        ? `/guilds/${guildId}/registration/${formId}/submissions?status=${submissionFilter}`
        : `/guilds/${guildId}/registration/${formId}/submissions`;
      const res = await api.get(url);
      setSubmissions(res.data.submissions || []);
    } catch (err) {
      console.error('Failed to load submissions', err);
    }
  };

  // Load Audit Logs
  const loadLogs = async () => {
    try {
      const res = await api.get(`/guilds/${guildId}/registration/logs`);
      setLogs(res.data.logs || []);
    } catch (err) {
      console.error('Failed to load logs', err);
    }
  };

  useEffect(() => {
    if (activeTab === 'logs') {
      loadLogs();
    }
  }, [activeTab]);

  useEffect(() => {
    if (activeTab === 'submissions' && selectedFormForSubmissions) {
      loadSubmissions(selectedFormForSubmissions);
    }
  }, [activeTab, selectedFormForSubmissions, submissionFilter]);

  // Load Questions for editing
  const loadQuestions = async (formId) => {
    try {
      const res = await api.get(`/guilds/${guildId}/registration/${formId}`);
      setQuestions(res.data.form?.questions || []);
      setSelectedFormForQuestions(res.data.form);
    } catch (err) {
      setError('Failed to load questions.');
    }
  };

  // Handle Save Form
  const handleSaveForm = async (e) => {
    e.preventDefault();
    setError('');
    try {
      if (editingForm) {
        await api.put(`/guilds/${guildId}/registration/${editingForm.id}`, formData);
        setSuccess('Form updated successfully!');
      } else {
        await api.post(`/guilds/${guildId}/registration`, formData);
        setSuccess('Form created successfully!');
      }
      setShowFormModal(false);
      setEditingForm(null);
      await fetchData();
      setTimeout(() => setSuccess(''), 3000);
    } catch (err) {
      setError(err.response?.data?.error || 'Failed to save form.');
    }
  };

  // Handle Delete Form
  const handleDeleteForm = async (formId, name) => {
    if (!window.confirm(`Are you sure you want to delete "${name}"? All questions and submissions will be deleted.`)) return;
    try {
      await api.delete(`/guilds/${guildId}/registration/${formId}`);
      await fetchData();
      setSuccess('Form deleted.');
      setTimeout(() => setSuccess(''), 3000);
    } catch (err) {
      setError('Failed to delete form.');
    }
  };

  // Handle Publish Panel
  const handlePublishPanel = async () => {
    if (!publishChannelId) {
      alert('Please select a channel.');
      return;
    }
    setPublishing(true);
    try {
      await api.post(`/guilds/${guildId}/registration/${publishModalForm.id}/publish`, {
        channel_id: publishChannelId,
      });
      setSuccess(`Published registration panel to selected channel!`);
      setPublishModalForm(null);
      await fetchData();
      setTimeout(() => setSuccess(''), 3000);
    } catch (err) {
      setError(err.response?.data?.error || 'Failed to publish panel.');
    }
    setPublishing(false);
  };

  // Handle Open Add Question Modal
  const handleOpenAddQuestion = () => {
    setEditingQuestion(null);
    setQuestionFormData({
      question: '',
      field_type: 'short_text',
      required: true,
      placeholder: '',
      options: '',
      min_length: '',
      max_length: '',
      min_value: '',
      max_value: '',
    });
    setShowQuestionModal(true);
  };

  // Handle Open Edit Question Modal
  const handleOpenEditQuestion = (q) => {
    setEditingQuestion(q);
    const optsStr = Array.isArray(q.options)
      ? q.options.join(', ')
      : (typeof q.options === 'string' ? q.options : '');
    setQuestionFormData({
      question: q.question || '',
      field_type: q.field_type || 'short_text',
      required: Boolean(q.required),
      placeholder: q.placeholder || '',
      options: optsStr,
      min_length: q.min_length != null ? q.min_length : '',
      max_length: q.max_length != null ? q.max_length : '',
      min_value: q.min_value != null ? q.min_value : '',
      max_value: q.max_value != null ? q.max_value : '',
    });
    setShowQuestionModal(true);
  };

  // Handle Save Question (Add or Edit)
  const handleSaveQuestion = async (e) => {
    e.preventDefault();
    try {
      const optsArray = questionFormData.options
        ? questionFormData.options.split(',').map(s => s.trim()).filter(Boolean)
        : [];
      const payload = {
        question: questionFormData.question.trim(),
        field_type: questionFormData.field_type,
        required: questionFormData.required,
        placeholder: questionFormData.placeholder.trim(),
        options: optsArray,
        min_length: questionFormData.min_length !== '' && questionFormData.min_length != null ? parseInt(questionFormData.min_length) : null,
        max_length: questionFormData.max_length !== '' && questionFormData.max_length != null ? parseInt(questionFormData.max_length) : null,
        min_value: questionFormData.min_value !== '' && questionFormData.min_value != null ? parseFloat(questionFormData.min_value) : null,
        max_value: questionFormData.max_value !== '' && questionFormData.max_value != null ? parseFloat(questionFormData.max_value) : null,
      };

      if (editingQuestion) {
        await api.put(`/guilds/${guildId}/registration/${selectedFormForQuestions.id}/questions/${editingQuestion.id}`, payload);
        setSuccess(`Question #${editingQuestion.id} updated successfully!`);
      } else {
        await api.post(`/guilds/${guildId}/registration/${selectedFormForQuestions.id}/questions`, payload);
        setSuccess('New question added to form!');
      }

      await loadQuestions(selectedFormForQuestions.id);
      setShowQuestionModal(false);
      setEditingQuestion(null);
      setTimeout(() => setSuccess(''), 3000);
    } catch (err) {
      setError(err.response?.data?.error || 'Failed to save question.');
    }
  };

  // Handle Move Question Up / Down
  const handleMoveQuestion = async (index, direction) => {
    const targetIndex = direction === 'up' ? index - 1 : index + 1;
    if (targetIndex < 0 || targetIndex >= questions.length) return;

    const reordered = [...questions];
    const [moved] = reordered.splice(index, 1);
    reordered.splice(targetIndex, 0, moved);
    setQuestions(reordered);

    try {
      const orderedIds = reordered.map(q => q.id);
      await api.put(`/guilds/${guildId}/registration/${selectedFormForQuestions.id}/questions/reorder`, {
        ordered_ids: orderedIds,
      });
      setSuccess('Question order saved.');
      setTimeout(() => setSuccess(''), 2000);
    } catch (err) {
      setError('Failed to save question reordering.');
      await loadQuestions(selectedFormForQuestions.id);
    }
  };

  // Handle Delete Question
  const handleDeleteQuestion = async (qId) => {
    if (!window.confirm('Delete this question?')) return;
    try {
      await api.delete(`/guilds/${guildId}/registration/${selectedFormForQuestions.id}/questions/${qId}`);
      await loadQuestions(selectedFormForQuestions.id);
    } catch (err) {
      setError('Failed to delete question.');
    }
  };

  // Handle Submission Review (Approve / Reject)
  const handleReviewSubmission = async (subId, action, reason = '') => {
    try {
      await api.post(`/guilds/${guildId}/registration/submissions/${subId}/review`, {
        action,
        reason,
      });
      setSuccess(`Application #${subId} marked as ${action.toUpperCase()}!`);
      setRejectingSubId(null);
      setRejectionReason('');
      if (selectedFormForSubmissions) {
        await loadSubmissions(selectedFormForSubmissions);
      }
      setTimeout(() => setSuccess(''), 3000);
    } catch (err) {
      setError(err.response?.data?.error || `Failed to ${action} submission.`);
    }
  };

  // Handle Delete / Remove Submission (Pending, Approved, or Rejected)
  const handleDeleteSubmission = async (sub) => {
    const isApproved = sub.status === 'approved';
    const confirmPrompt = isApproved
      ? `Permanently delete Application #${sub.id} for user ${sub.user_id}?\n\nThis will also revoke and remove any server roles assigned upon approval.\n\nClick OK to confirm.`
      : `Permanently delete Application #${sub.id} for user ${sub.user_id}?`;

    if (!window.confirm(confirmPrompt)) return;

    try {
      await api.delete(`/guilds/${guildId}/registration/submissions/${sub.id}?revoke_roles=true`);
      setSuccess(`Application #${sub.id} deleted successfully.${isApproved ? ' Assigned roles revoked.' : ''}`);
      if (selectedFormForSubmissions) {
        await loadSubmissions(selectedFormForSubmissions);
      }
      setTimeout(() => setSuccess(''), 3000);
    } catch (err) {
      setError(err.response?.data?.error || 'Failed to delete application.');
    }
  };

  if (loading) {
    return (
      <div className="animate-fade-in stagger">
        <div className="skeleton" style={{ height: '80px', marginBottom: '24px' }}></div>
        <div className="skeleton" style={{ height: '300px' }}></div>
      </div>
    );
  }

  return (
    <div className="animate-fade-in" style={{ paddingBottom: '60px' }}>
      {/* Header */}
      <div className="page-header flex justify-between items-center" style={{ flexWrap: 'wrap', gap: '12px' }}>
        <div>
          <h1 className="page-title">📝 Dynamic Registration & Applications</h1>
          <p className="page-subtitle">Build custom application forms, configure multi-role & nickname automations, and manage applicant submissions.</p>
        </div>
        <div className="flex gap-2">
          <button className="btn btn-ghost" onClick={() => { setLoading(true); fetchData(); }}>
            ↻ Refresh
          </button>
          <button
            className="btn btn-primary"
            onClick={() => {
              setEditingForm(null);
              setFormData({
                name: '',
                description: '',
                button_label: 'Register',
                button_emoji: '📝',
                button_style: 'primary',
                channel_id: '',
                enabled: true,
                approval_mode: 'automatic',
                review_channel_id: '',
                log_channel_id: '',
                auto_role_enabled: false,
                add_role_ids: [],
                remove_role_enabled: false,
                remove_role_ids: [],
                change_nickname_enabled: false,
                nickname_question_id: null,
                nickname_format: '{name}',
                single_submission: true,
                success_message: 'Your registration has been submitted successfully!',
              });
              setShowFormModal(true);
            }}
          >
            ➕ Create Form
          </button>
        </div>
      </div>

      {/* Alerts */}
      {error && <div className="alert alert-error mb-4">⚠️ {error}</div>}
      {success && <div className="alert alert-success mb-4">✅ {success}</div>}

      {/* Tabs */}
      <div className="flex gap-2 mb-6 border-b border-border pb-2">
        <button
          className={`btn ${activeTab === 'forms' ? 'btn-primary' : 'btn-ghost'}`}
          onClick={() => { setActiveTab('forms'); setSelectedFormForQuestions(null); }}
        >
          📋 Registration Forms ({forms.length})
        </button>
        <button
          className={`btn ${activeTab === 'submissions' ? 'btn-primary' : 'btn-ghost'}`}
          onClick={() => {
            setActiveTab('submissions');
            if (forms.length > 0 && !selectedFormForSubmissions) {
              setSelectedFormForSubmissions(forms[0].id);
            }
          }}
        >
          📥 Submissions & Review
        </button>
        <button
          className={`btn ${activeTab === 'logs' ? 'btn-primary' : 'btn-ghost'}`}
          onClick={() => setActiveTab('logs')}
        >
          📜 Audit & Activity Logs
        </button>
      </div>

      {/* TAB 1: FORMS & QUESTION BUILDER */}
      {activeTab === 'forms' && (
        <div>
          {selectedFormForQuestions ? (
            /* Question Manager View */
            <div className="card">
              <div className="flex justify-between items-center mb-6">
                <div>
                  <button className="btn btn-ghost btn-sm mb-2" onClick={() => setSelectedFormForQuestions(null)}>
                    ⬅️ Back to Forms List
                  </button>
                  <h2 className="text-xl font-bold">Questions for "{selectedFormForQuestions.name}"</h2>
                  <p className="text-muted text-sm">Configure fields presented in the dynamic Discord form & modal.</p>
                </div>
                <button className="btn btn-primary" onClick={handleOpenAddQuestion}>
                  ➕ Add Question
                </button>
              </div>

              {questions.length === 0 ? (
                <div className="text-center p-8 text-muted">
                  No questions configured yet. Click <strong>Add Question</strong> to create your first field.
                </div>
              ) : (
                <div className="flex flex-col gap-3">
                  {questions.map((q, idx) => (
                    <div key={q.id} className="card bg-surface flex justify-between items-center p-4 border border-border">
                      <div className="flex items-center gap-3">
                        {/* Reorder Buttons */}
                        <div className="flex flex-col gap-1">
                          <button
                            type="button"
                            className="btn btn-ghost btn-xs p-1"
                            style={{ lineHeight: 1, minHeight: 'auto', height: '22px', width: '22px' }}
                            disabled={idx === 0}
                            onClick={() => handleMoveQuestion(idx, 'up')}
                            title="Move Up"
                          >
                            ▲
                          </button>
                          <button
                            type="button"
                            className="btn btn-ghost btn-xs p-1"
                            style={{ lineHeight: 1, minHeight: 'auto', height: '22px', width: '22px' }}
                            disabled={idx === questions.length - 1}
                            onClick={() => handleMoveQuestion(idx, 'down')}
                            title="Move Down"
                          >
                            ▼
                          </button>
                        </div>

                        <div>
                          <div className="flex items-center gap-2 mb-1">
                            <span className="font-bold text-accent">#{idx + 1}</span>
                            <span className="font-semibold text-base">{q.question}</span>
                            {q.required ? (
                              <span className="badge badge-danger text-xs">Required</span>
                            ) : (
                              <span className="badge badge-secondary text-xs">Optional</span>
                            )}
                          </div>
                          <div className="text-sm text-muted">
                            Format: <strong className="text-primary font-mono">{FIELD_TYPES.find(t => t.value === q.field_type)?.label || q.field_type}</strong>
                            {q.placeholder && <span> • Placeholder: "{q.placeholder}"</span>}
                            {q.options && q.options.length > 0 && <span> • Choices ({q.options.length}): [{q.options.slice(0, 5).join(', ')}{q.options.length > 5 ? ` +${q.options.length - 5} more` : ''}]</span>}
                            {q.min_length != null && <span> • Min Length: {q.min_length}</span>}
                            {q.max_length != null && <span> • Max Length: {q.max_length}</span>}
                            {q.min_value != null && <span> • Min: {q.min_value}</span>}
                            {q.max_value != null && <span> • Max: {q.max_value}</span>}
                          </div>
                        </div>
                      </div>

                      <div className="flex items-center gap-2">
                        <button
                          className="btn btn-secondary btn-sm"
                          onClick={() => handleOpenEditQuestion(q)}
                          title="Edit Question & Format"
                        >
                          ✏️ Edit
                        </button>
                        <button
                          className="btn btn-danger btn-sm"
                          onClick={() => handleDeleteQuestion(q.id)}
                          title="Delete Question"
                        >
                          🗑️ Delete
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          ) : (
            /* Forms List View */
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              {forms.length === 0 ? (
                <div className="card col-span-2 text-center p-12 text-muted">
                  <div style={{ fontSize: '48px', marginBottom: '16px' }}>📝</div>
                  <h3 className="text-lg font-bold mb-2">No Registration Forms Configured</h3>
                  <p className="mb-4">Click "Create Form" to set up your server application system.</p>
                </div>
              ) : (
                forms.map((f) => (
                  <div key={f.id} className="card flex flex-col justify-between">
                    <div>
                      <div className="flex justify-between items-start mb-2">
                        <h3 className="text-lg font-bold">{f.name}</h3>
                        <span className={`badge ${f.enabled ? 'badge-success' : 'badge-secondary'}`}>
                          {f.enabled ? '🟢 Enabled' : '🔴 Disabled'}
                        </span>
                      </div>
                      <p className="text-sm text-muted mb-4">{f.description || 'No description provided.'}</p>

                      <div className="grid grid-cols-2 gap-2 text-xs text-muted mb-4 bg-surface p-3 rounded-lg border border-border">
                        <div>📝 Questions: <strong className="text-foreground">{f.question_count}</strong></div>
                        <div>📊 Submissions: <strong className="text-foreground">{f.submission_count}</strong></div>
                        <div>⚖️ Approval: <strong className="text-foreground">{f.approval_mode === 'automatic' ? '⚡ Auto' : '🛡️ Review'}</strong></div>
                        <div>
                          📍 Channel: {f.channel_id ? (
                            <strong className="text-accent">#{channels.find(c => c.id === f.channel_id)?.name || f.channel_id}</strong>
                          ) : (
                            <span>Not published</span>
                          )}
                        </div>
                        {f.auto_role_enabled && (
                          <div className="col-span-2 text-emerald-400">
                            🛡️ Auto-Roles: {f.add_role_ids?.length || 0} role(s) configured
                          </div>
                        )}
                        {f.change_nickname_enabled && (
                          <div className="col-span-2 text-blue-400">
                            🏷️ Nickname Change: Active (Format: <code>{f.nickname_format}</code>)
                          </div>
                        )}
                      </div>
                    </div>

                    <div className="flex flex-wrap gap-2 pt-2 border-t border-border">
                      <button
                        className="btn btn-primary btn-sm"
                        onClick={() => {
                          setPublishModalForm(f);
                          setPublishChannelId(f.channel_id || (channels[0]?.id || ''));
                        }}
                      >
                        📢 Publish Panel
                      </button>
                      <button
                        className="btn btn-secondary btn-sm"
                        onClick={() => loadQuestions(f.id)}
                      >
                        📋 Questions ({f.question_count})
                      </button>
                      <button
                        className="btn btn-ghost btn-sm"
                        onClick={async () => {
                          const res = await api.get(`/guilds/${guildId}/registration/${f.id}`);
                          const full = res.data.form;
                          setEditingForm(full);
                          setFormData({
                            name: full.name || '',
                            description: full.description || '',
                            button_label: full.button_label || 'Register',
                            button_emoji: full.button_emoji || '📝',
                            button_style: full.button_style || 'primary',
                            channel_id: full.channel_id || '',
                            enabled: full.enabled,
                            approval_mode: full.approval_mode || 'automatic',
                            review_channel_id: full.review_channel_id || '',
                            log_channel_id: full.log_channel_id || '',
                            auto_role_enabled: full.auto_role_enabled || false,
                            add_role_ids: full.add_role_ids || [],
                            remove_role_enabled: full.remove_role_enabled || false,
                            remove_role_ids: full.remove_role_ids || [],
                            change_nickname_enabled: full.change_nickname_enabled || false,
                            nickname_question_id: full.nickname_question_id || null,
                            nickname_format: full.nickname_format || '{name}',
                            single_submission: full.single_submission !== false,
                            success_message: full.success_message || '',
                          });
                          setShowFormModal(true);
                        }}
                      >
                        ⚙️ Settings & Automations
                      </button>
                      <button
                        className="btn btn-danger btn-sm ml-auto"
                        onClick={() => handleDeleteForm(f.id, f.name)}
                      >
                        🗑️
                      </button>
                    </div>
                  </div>
                ))
              )}
            </div>
          )}
        </div>
      )}

      {/* TAB 2: SUBMISSIONS & REVIEW */}
      {activeTab === 'submissions' && (
        <div className="card">
          <div className="flex flex-wrap justify-between items-center mb-6 gap-4">
            <div>
              <h2 className="text-xl font-bold">Member Applications & Submissions</h2>
              <p className="text-muted text-sm">Review, approve, or reject applicant submissions and trigger configured automations.</p>
            </div>
            <div className="flex gap-3">
              {/* Form Selector */}
              <div style={{ minWidth: '200px' }}>
                <Select
                  value={selectedFormForSubmissions}
                  onChange={(val) => setSelectedFormForSubmissions(val)}
                  options={forms.map(f => ({ value: f.id, label: f.name }))}
                  placeholder="Select Form..."
                />
              </div>
              {/* Status Filter */}
              <div style={{ minWidth: '150px' }}>
                <Select
                  value={submissionFilter}
                  onChange={(val) => setSubmissionFilter(val)}
                  options={[
                    { value: 'all', label: 'All Statuses' },
                    { value: 'pending', label: '🟡 Pending' },
                    { value: 'approved', label: '✅ Approved' },
                    { value: 'rejected', label: '❌ Rejected' },
                  ]}
                />
              </div>
            </div>
          </div>

          {submissions.length === 0 ? (
            <div className="text-center p-12 text-muted">
              No submissions found matching the criteria.
            </div>
          ) : (
            <div className="flex flex-col gap-4">
              {submissions.map((sub) => (
                <div key={sub.id} className="card bg-surface border border-border p-4">
                  <div className="flex justify-between items-start mb-3">
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="font-bold text-lg">Application #{sub.id}</span>
                        <span className={`badge ${
                          sub.status === 'approved' ? 'badge-success' : sub.status === 'rejected' ? 'badge-danger' : 'badge-warning'
                        }`}>
                          {sub.status.toUpperCase()}
                        </span>
                      </div>
                      <div className="text-xs text-muted mt-1">
                        Applicant User ID: <code>{sub.user_id}</code> • Submitted: {new Date(sub.submitted_at).toLocaleString()}
                        {sub.reviewed_by && <span> • Reviewed by: <code>{sub.reviewed_by}</code></span>}
                      </div>
                    </div>

                    {sub.status === 'pending' && (
                      <div className="flex gap-2">
                        <button
                          className="btn btn-success btn-sm"
                          onClick={() => handleReviewSubmission(sub.id, 'approve')}
                        >
                          ✅ Approve
                        </button>
                        <button
                          className="btn btn-danger btn-sm"
                          onClick={() => setRejectingSubId(sub.id)}
                        >
                          ❌ Reject
                        </button>
                      </div>
                    )}
                  </div>

                  {/* Answers Accordion / Content */}
                  <div className="bg-background p-3 rounded-lg border border-border mt-3">
                    <div className="text-xs font-bold text-muted uppercase mb-2">Submitted Answers:</div>
                    <div className="flex flex-col gap-2">
                      {sub.answers.map((ans, aIdx) => (
                        <div key={aIdx} className="text-sm">
                          <strong className="text-accent">{ans.question_text}:</strong>{' '}
                          <span className="text-foreground">{ans.answer || '—'}</span>
                        </div>
                      ))}
                    </div>
                  </div>

                  {sub.rejection_reason && (
                    <div className="mt-2 text-xs text-danger">
                      <strong>Rejection Reason:</strong> {sub.rejection_reason}
                    </div>
                  )}

                  {/* Inline Rejection Reason Prompt */}
                  {rejectingSubId === sub.id && (
                    <div className="mt-3 p-3 bg-red-950/30 border border-red-800/50 rounded-lg">
                      <label className="block text-sm font-semibold mb-1">Reason for Rejection (Optional):</label>
                      <input
                        type="text"
                        className="input mb-2"
                        placeholder="e.g. Does not meet requirements..."
                        value={rejectionReason}
                        onChange={(e) => setRejectionReason(e.target.value)}
                      />
                      <div className="flex gap-2">
                        <button
                          className="btn btn-danger btn-sm"
                          onClick={() => handleReviewSubmission(sub.id, 'reject', rejectionReason)}
                        >
                          Confirm Rejection
                        </button>
                        <button
                          className="btn btn-ghost btn-sm"
                          onClick={() => { setRejectingSubId(null); setRejectionReason(''); }}
                        >
                          Cancel
                        </button>
                      </div>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* TAB 3: AUDIT & ACTIVITY LOGS */}
      {activeTab === 'logs' && (
        <div className="card">
          <div className="flex justify-between items-center mb-6">
            <div>
              <h2 className="text-xl font-bold">Registration Audit & Automation Logs</h2>
              <p className="text-muted text-sm">Chronological record of form edits, submissions, staff reviews, and post-registration automations.</p>
            </div>
            <button className="btn btn-ghost" onClick={loadLogs}>
              ↻ Refresh Logs
            </button>
          </div>

          {logs.length === 0 ? (
            <div className="text-center p-12 text-muted">No registration activity recorded yet.</div>
          ) : (
            <div className="table-responsive">
              <table className="table">
                <thead>
                  <tr>
                    <th>Timestamp</th>
                    <th>Event Type</th>
                    <th>Details</th>
                    <th>Target / Actor</th>
                  </tr>
                </thead>
                <tbody>
                  {logs.map((l) => (
                    <tr key={l.id}>
                      <td className="text-xs text-muted whitespace-nowrap">
                        {new Date(l.created_at).toLocaleString()}
                      </td>
                      <td>
                        <span className="badge badge-secondary text-xs">
                          {l.event_type.replace('_', ' ').toUpperCase()}
                        </span>
                      </td>
                      <td className="text-sm font-medium">{l.details}</td>
                      <td className="text-xs text-muted">
                        {l.target_user_id && <div>Target: <code>{l.target_user_id}</code></div>}
                        {l.actor_id && <div>Actor: <code>{l.actor_id}</code></div>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* MODAL: CREATE / EDIT FORM & AUTOMATIONS */}
      {showFormModal && (
        <div className="modal-backdrop">
          <div className="modal card" style={{ maxWidth: '650px', maxHeight: '90vh', overflowY: 'auto' }}>
            <div className="flex justify-between items-center mb-4">
              <h3 className="text-xl font-bold">{editingForm ? 'Edit Form & Automations' : 'Create Registration Form'}</h3>
              <button className="btn btn-ghost btn-sm" onClick={() => setShowFormModal(false)}>✕</button>
            </div>

            <form onSubmit={handleSaveForm}>
              <div className="form-group mb-4">
                <label className="label">Form Name</label>
                <input
                  type="text"
                  className="input"
                  required
                  placeholder="e.g. Server Registration, Whitelist Application"
                  value={formData.name}
                  onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                />
              </div>

              <div className="form-group mb-4">
                <label className="label">Description / Instructions</label>
                <textarea
                  className="input"
                  rows="3"
                  placeholder="Explain requirements or welcome instructions for the applicant..."
                  value={formData.description}
                  onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                />
              </div>

              {/* Panel Button Styling */}
              <div className="grid grid-cols-3 gap-3 mb-4">
                <div>
                  <label className="label">Button Label</label>
                  <input
                    type="text"
                    className="input"
                    value={formData.button_label}
                    onChange={(e) => setFormData({ ...formData, button_label: e.target.value })}
                  />
                </div>
                <div>
                  <label className="label">Button Emoji</label>
                  <input
                    type="text"
                    className="input"
                    value={formData.button_emoji}
                    onChange={(e) => setFormData({ ...formData, button_emoji: e.target.value })}
                  />
                </div>
                <div>
                  <label className="label">Button Style</label>
                  <Select
                    value={formData.button_style}
                    onChange={(val) => setFormData({ ...formData, button_style: val })}
                    options={[
                      { value: 'primary', label: 'Blurple' },
                      { value: 'secondary', label: 'Grey' },
                      { value: 'success', label: 'Green' },
                      { value: 'danger', label: 'Red' },
                    ]}
                  />
                </div>
              </div>

              {/* Approval Mode & Channels */}
              <div className="card bg-surface p-4 mb-4 border border-border">
                <h4 className="font-bold text-sm mb-3">⚙️ Review & Notification Settings</h4>
                <div className="grid grid-cols-2 gap-3 mb-3">
                  <div>
                    <label className="label">Approval Workflow</label>
                    <Select
                      value={formData.approval_mode}
                      onChange={(val) => setFormData({ ...formData, approval_mode: val })}
                      options={[
                        { value: 'automatic', label: '⚡ Automatic Approval' },
                        { value: 'staff_review', label: '🛡️ Staff Review Required' },
                      ]}
                    />
                  </div>
                  <div>
                    <label className="label">Staff Review Channel</label>
                    <Select
                      value={formData.review_channel_id}
                      onChange={(val) => setFormData({ ...formData, review_channel_id: val })}
                      options={[
                        { value: '', label: 'None (Disabled)' },
                        ...channels.map(c => ({ value: c.id, label: `#${c.name}` })),
                      ]}
                    />
                  </div>
                </div>

                <div>
                  <label className="label">Registration Audit Log Channel</label>
                  <Select
                    value={formData.log_channel_id}
                    onChange={(val) => setFormData({ ...formData, log_channel_id: val })}
                    options={[
                      { value: '', label: 'None (Disabled)' },
                      ...channels.map(c => ({ value: c.id, label: `#${c.name}` })),
                    ]}
                  />
                </div>
              </div>

              {/* Automations: Roles */}
              <div className="card bg-surface p-4 mb-4 border border-border">
                <h4 className="font-bold text-sm mb-3">🛡️ Post-Registration Role Automations</h4>
                <div className="mb-3">
                  <label className="flex items-center gap-2 cursor-pointer mb-2">
                    <input
                      type="checkbox"
                      checked={formData.auto_role_enabled}
                      onChange={(e) => setFormData({ ...formData, auto_role_enabled: e.target.checked })}
                    />
                    <span className="text-sm font-semibold">Grant Roles Upon Approval</span>
                  </label>
                  {formData.auto_role_enabled && (
                    <MultiSelect
                      values={formData.add_role_ids}
                      onChange={(vals) => setFormData({ ...formData, add_role_ids: vals })}
                      options={roles.map(r => ({ value: r.id, label: `@${r.name}` }))}
                      placeholder="Select roles to add..."
                    />
                  )}
                </div>

                <div>
                  <label className="flex items-center gap-2 cursor-pointer mb-2">
                    <input
                      type="checkbox"
                      checked={formData.remove_role_enabled}
                      onChange={(e) => setFormData({ ...formData, remove_role_enabled: e.target.checked })}
                    />
                    <span className="text-sm font-semibold">Remove Roles Upon Approval (e.g. Unverified)</span>
                  </label>
                  {formData.remove_role_enabled && (
                    <MultiSelect
                      values={formData.remove_role_ids}
                      onChange={(vals) => setFormData({ ...formData, remove_role_ids: vals })}
                      options={roles.map(r => ({ value: r.id, label: `@${r.name}` }))}
                      placeholder="Select roles to remove..."
                    />
                  )}
                </div>
              </div>

              {/* Automations: Nickname Change */}
              <div className="card bg-surface p-4 mb-4 border border-border">
                <h4 className="font-bold text-sm mb-3">🏷️ Member Nickname Change Automation</h4>
                <label className="flex items-center gap-2 cursor-pointer mb-3">
                  <input
                    type="checkbox"
                    checked={formData.change_nickname_enabled}
                    onChange={(e) => setFormData({ ...formData, change_nickname_enabled: e.target.checked })}
                  />
                  <span className="text-sm font-semibold">Automatically Update Member's Server Nickname</span>
                </label>

                {formData.change_nickname_enabled && (
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <label className="label">Nickname Format Template</label>
                      <input
                        type="text"
                        className="input"
                        placeholder="{name} or [Member] {name}"
                        value={formData.nickname_format}
                        onChange={(e) => setFormData({ ...formData, nickname_format: e.target.value })}
                      />
                      <span className="text-xs text-muted">Use <code>{'{name}'}</code> where the answer will be placed.</span>
                    </div>
                    <div>
                      <label className="label">Source Question ID (Optional)</label>
                      <input
                        type="number"
                        className="input"
                        placeholder="Question ID from Questions tab"
                        value={formData.nickname_question_id || ''}
                        onChange={(e) => setFormData({ ...formData, nickname_question_id: e.target.value ? parseInt(e.target.value) : null })}
                      />
                    </div>
                  </div>
                )}
              </div>

              {/* Restriction Flags */}
              <div className="mb-4">
                <label className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={formData.single_submission}
                    onChange={(e) => setFormData({ ...formData, single_submission: e.target.checked })}
                  />
                  <span className="text-sm">Prevent duplicate registrations (single submission per member)</span>
                </label>
              </div>

              <div className="flex justify-end gap-2 pt-3 border-t border-border">
                <button type="button" className="btn btn-ghost" onClick={() => setShowFormModal(false)}>
                  Cancel
                </button>
                <button type="submit" className="btn btn-primary">
                  {editingForm ? 'Save Changes' : 'Create Form'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* MODAL: ADD / EDIT QUESTION */}
      {showQuestionModal && (
        <div className="modal-backdrop">
          <div className="modal card" style={{ maxWidth: '580px', width: '100%' }}>
            <div className="flex justify-between items-center mb-4">
              <div>
                <h3 className="text-lg font-bold">
                  {editingQuestion ? `✏️ Edit Question #${editingQuestion.id}` : '➕ Add Question to Form'}
                </h3>
                <p className="text-xs text-muted">
                  {editingQuestion
                    ? 'Modify the question text, response format, choices, and validation constraints.'
                    : 'Create a new dynamic field for this registration form.'}
                </p>
              </div>
              <button className="btn btn-ghost btn-sm" onClick={() => setShowQuestionModal(false)}>✕</button>
            </div>

            <form onSubmit={handleSaveQuestion}>
              <div className="form-group mb-3">
                <label className="label">Question Text / Title *</label>
                <input
                  type="text"
                  className="input"
                  required
                  placeholder="e.g. In-Game Name (IGN) & Tagline"
                  value={questionFormData.question}
                  onChange={(e) => setQuestionFormData({ ...questionFormData, question: e.target.value })}
                />
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mb-3">
                <div>
                  <label className="label">Format / Question Type *</label>
                  <Select
                    value={questionFormData.field_type}
                    onChange={(val) => setQuestionFormData({ ...questionFormData, field_type: val })}
                    options={FIELD_TYPES}
                  />
                </div>
                <div>
                  <label className="label">Is Required? *</label>
                  <Select
                    value={questionFormData.required ? 'yes' : 'no'}
                    onChange={(val) => setQuestionFormData({ ...questionFormData, required: val === 'yes' })}
                    options={[
                      { value: 'yes', label: 'Yes (Mandatory)' },
                      { value: 'no', label: 'No (Optional)' },
                    ]}
                  />
                </div>
              </div>

              <div className="form-group mb-3">
                <label className="label">Placeholder / Help Text (Optional)</label>
                <input
                  type="text"
                  className="input"
                  placeholder="e.g. PlayerName#1234..."
                  value={questionFormData.placeholder}
                  onChange={(e) => setQuestionFormData({ ...questionFormData, placeholder: e.target.value })}
                />
              </div>

              {/* Options for Select dropdowns */}
              {(questionFormData.field_type === 'single_select' || questionFormData.field_type === 'multiple_select') && (
                <div className="form-group mb-3 bg-surface p-3 rounded-lg border border-border">
                  <label className="label font-semibold">Choices / Options (Comma-separated) *</label>
                  <textarea
                    className="input"
                    rows={3}
                    placeholder="Iron 1, Iron 2, Bronze 1, Silver 1, Gold 1, Platinum 1, Diamond 1, Ascendant 1, Immortal 1, Radiant"
                    value={questionFormData.options}
                    onChange={(e) => setQuestionFormData({ ...questionFormData, options: e.target.value })}
                    required
                  />
                  <span className="text-xs text-muted mt-1 block">
                    Separate each selectable choice with a comma. Discord supports up to 25 choices per component (larger lists are automatically partitioned).
                  </span>
                </div>
              )}

              {/* Numeric Constraints */}
              {questionFormData.field_type === 'number' && (
                <div className="grid grid-cols-2 gap-3 mb-3 bg-surface p-3 rounded-lg border border-border">
                  <div>
                    <label className="label">Minimum Value</label>
                    <input
                      type="number"
                      className="input"
                      placeholder="e.g. 1"
                      value={questionFormData.min_value}
                      onChange={(e) => setQuestionFormData({ ...questionFormData, min_value: e.target.value })}
                    />
                  </div>
                  <div>
                    <label className="label">Maximum Value</label>
                    <input
                      type="number"
                      className="input"
                      placeholder="e.g. 100"
                      value={questionFormData.max_value}
                      onChange={(e) => setQuestionFormData({ ...questionFormData, max_value: e.target.value })}
                    />
                  </div>
                </div>
              )}

              {/* Text Length Constraints */}
              {(questionFormData.field_type === 'short_text' || questionFormData.field_type === 'paragraph') && (
                <div className="grid grid-cols-2 gap-3 mb-3 bg-surface p-3 rounded-lg border border-border">
                  <div>
                    <label className="label">Minimum Characters (Optional)</label>
                    <input
                      type="number"
                      className="input"
                      placeholder="e.g. 3"
                      value={questionFormData.min_length}
                      onChange={(e) => setQuestionFormData({ ...questionFormData, min_length: e.target.value })}
                    />
                  </div>
                  <div>
                    <label className="label">Maximum Characters (Optional)</label>
                    <input
                      type="number"
                      className="input"
                      placeholder="e.g. 100"
                      value={questionFormData.max_length}
                      onChange={(e) => setQuestionFormData({ ...questionFormData, max_length: e.target.value })}
                    />
                  </div>
                </div>
              )}

              <div className="flex justify-end gap-2 pt-3 border-t border-border mt-4">
                <button type="button" className="btn btn-ghost" onClick={() => setShowQuestionModal(false)}>
                  Cancel
                </button>
                <button type="submit" className="btn btn-primary">
                  {editingQuestion ? '💾 Save Question Changes' : '➕ Add Question'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* MODAL: PUBLISH PANEL */}
      {publishModalForm && (
        <div className="modal-backdrop">
          <div className="modal card" style={{ maxWidth: '450px' }}>
            <h3 className="text-lg font-bold mb-2">Publish Registration Panel</h3>
            <p className="text-sm text-muted mb-4">
              Send the registration embed and interactive button for <strong>"{publishModalForm.name}"</strong> to a Discord channel.
            </p>

            <div className="form-group mb-4">
              <label className="label">Select Channel</label>
              <Select
                value={publishChannelId}
                onChange={(val) => setPublishChannelId(val)}
                options={channels.map(c => ({ value: c.id, label: `#${c.name}` }))}
              />
            </div>

            <div className="flex justify-end gap-2">
              <button className="btn btn-ghost" onClick={() => setPublishModalForm(null)}>
                Cancel
              </button>
              <button className="btn btn-primary" disabled={publishing} onClick={handlePublishPanel}>
                {publishing ? 'Publishing...' : '📢 Publish Now'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default Registration;
