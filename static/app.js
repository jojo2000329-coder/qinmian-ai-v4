/**
 * 勤勉 AI v4 — 主前端应用
 * 
 * 新增功能：
 * - 粒子动效系统（Canvas 晴空云絮）
 * - 全屏 AI 助手页面（天蓝主题）
 * - 开场动画（Splash Screen）
 * - 对话管理（新建/查询/删除）
 * - 知识库（长期记忆）开关
 * - 大模型开关
 * - 浮动聊天与全屏页面的协同
 */

// ═════════════════════════════════════════════════════════════════════
// 状态管理
// ═════════════════════════════════════════════════════════════════════

const state = {
  user: null,
  meta: null,
  majors: [],
  selectedMajor: null,
  curriculum: null,
  hot: null,
  careerProfiles: null,
  careerRecommendations: null,
  careerPlan: null,
  teacherRoster: null,
  teacherRosterFilters: { college: "", q: "", scheduled: "" },
  facultyProfiles: null,
  facultyFilters: { college: "", rank: "", q: "", tutor: "" },
  lastTeacherName: "",
  persona: "diligent",
  studentType: "domestic",
  activeTab: "profile",
  floatingChatOpen: true,
  chatBusy: false,
  chat: [
    {
      role: "assistant",
      text: "我是勤勉。你可以问我：算法工程师怎么规划完整学习路线？机器学习硬核吗？人工智能毕业学分是多少？",
      suggestions: ["这个专业适合哪些职业", "算法工程师完整学习路线", "机器学习硬核吗"],
    },
  ],

  // AI 全屏页面状态
  aiPageOpen: false,
  activeConvId: null,
  conversations: [],
  aiConversation: [],
  aiChatBusy: false,

  // 开关
  llmEnabled: false,
  llmConfig: null,
  memoryEnabled: true,

  // 粒子系统
  particleInitialized: false,
};

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => document.querySelectorAll(selector);

// ═════════════════════════════════════════════════════════════════════
// 粒子系统 — 放射性尘埃效果
// ═════════════════════════════════════════════════════════════════════

class ParticleSystem {
  constructor(canvas) {
    this.canvas = canvas;
    this.ctx = canvas.getContext("2d");
    this.particles = [];
    this.stars = [];       // ★ 星空层
    this.radiantBursts = [];
    this.mouseX = -1000;
    this.mouseY = -1000;
    this.animId = null;

    this.resize();
    window.addEventListener("resize", () => this.resize());

    document.addEventListener("mousemove", (e) => {
      this.mouseX = e.clientX;
      this.mouseY = e.clientY;
    });

    this.init();
  }

  resize() {
    this.canvas.width = window.innerWidth;
    this.canvas.height = window.innerHeight;
  }

  init() {
    // ★ 初始化星空（静态分布，数量较多）
    const starCount = Math.min(200, Math.floor(window.innerWidth * window.innerHeight / 8000));
    for (let i = 0; i < starCount; i++) {
      this.stars.push({
        x: Math.random() * this.canvas.width,
        y: Math.random() * this.canvas.height,
        size: Math.random() * 2 + 0.3,
        alpha: Math.random() * 0.7 + 0.2,
        twinkleSpeed: Math.random() * 0.02 + 0.005,
        twinklePhase: Math.random() * Math.PI * 2,
        driftX: (Math.random() - 0.5) * 0.05,
        driftY: (Math.random() - 0.5) * 0.05,
      });
    }

    // 蓝色云絮粒子
    const count = Math.min(80, Math.floor(window.innerWidth * window.innerHeight / 12000));
    for (let i = 0; i < count; i++) {
      this.particles.push(this._createParticle(true));
    }
  }

  _createParticle(randomize = false) {
    const cx = this.canvas.width / 2;
    const cy = this.canvas.height / 2;
    const angle = Math.random() * Math.PI * 2;
    const radius = randomize ? Math.random() * Math.max(this.canvas.width, this.canvas.height) * 0.6 : 0;

    return {
      x: cx + Math.cos(angle) * radius,
      y: cy + Math.sin(angle) * radius,
      vx: (Math.random() - 0.5) * 0.3,
      vy: (Math.random() - 0.5) * 0.3,
      size: Math.random() * 3 + 0.5,
      alpha: Math.random() * 0.4 + 0.08,
      life: Math.random() * 1 + 0.2,
      maxLife: Math.random() * 1 + 0.2,
      hue: Math.random() > 0.5 ? 200 : 230,
      pulse: Math.random() * Math.PI * 2,
      pulseSpeed: Math.random() * 0.02 + 0.005,
    };
  }

  addBurst(x, y, count = 12) {
    for (let i = 0; i < count; i++) {
      const angle = (Math.PI * 2 * i) / count + Math.random() * 0.3;
      const speed = Math.random() * 1.5 + 0.8;
      this.particles.push({
        x,
        y,
        vx: Math.cos(angle) * speed,
        vy: Math.sin(angle) * speed,
        size: Math.random() * 2.5 + 0.5,
        alpha: 0.6,
        life: 0,
        maxLife: Math.random() * 0.8 + 0.3,
        hue: Math.random() > 0.5 ? 200 : 230,
        pulse: 0,
        pulseSpeed: 0.02,
      });
    }
  }

  animate() {
    this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);

    const cx = this.canvas.width / 2;
    const cy = this.canvas.height / 2;

    // ── 1. 绘制星空层 ────────────────────────────────────
    for (let i = 0; i < this.stars.length; i++) {
      const s = this.stars[i];

      // 缓慢漂移
      s.x += s.driftX;
      s.y += s.driftY;

      // 边界回绕
      if (s.x < -10) s.x = this.canvas.width + 10;
      if (s.x > this.canvas.width + 10) s.x = -10;
      if (s.y < -10) s.y = this.canvas.height + 10;
      if (s.y > this.canvas.height + 10) s.y = -10;

      // 闪烁
      s.twinklePhase += s.twinkleSpeed;
      const twinkle = Math.sin(s.twinklePhase) * 0.4 + 0.6;
      const starAlpha = s.alpha * twinkle * 0.8;

      this.ctx.beginPath();
      this.ctx.arc(s.x, s.y, s.size, 0, Math.PI * 2);
      this.ctx.fillStyle = `rgba(255, 255, 255, ${starAlpha})`;

      // 大星星带微光晕
      if (s.size > 1.2) {
        this.ctx.shadowBlur = 6;
        this.ctx.shadowColor = `rgba(255, 255, 255, ${starAlpha * 0.3})`;
      }
      this.ctx.fill();
      this.ctx.shadowBlur = 0;
    }

    // ── 2. 中心光晕 ──────────────────────────────────────
    const glowGrad = this.ctx.createRadialGradient(cx, cy, 0, cx, cy, Math.max(cx, cy) * 0.15);
    glowGrad.addColorStop(0, "rgba(14, 165, 233, 0.04)");
    glowGrad.addColorStop(0.5, "rgba(59, 130, 246, 0.02)");
    glowGrad.addColorStop(1, "rgba(255, 255, 255, 0)");
    this.ctx.fillStyle = glowGrad;
    this.ctx.fillRect(0, 0, this.canvas.width, this.canvas.height);

    // ── 3. 蓝色云絮粒子 ──────────────────────────────────
    const particleCount = this.particles.length;
    for (let i = particleCount - 1; i >= 0; i--) {
      const p = this.particles[i];

      p.x += p.vx;
      p.y += p.vy;
      p.life += 0.005;

      // 缓慢向外漂移
      const dx = p.x - cx;
      const dy = p.y - cy;
      const dist = Math.sqrt(dx * dx + dy * dy);
      if (dist > 10) {
        p.vx += (dx / dist) * 0.0005;
        p.vy += (dy / dist) * 0.0005;
      }

      // 速度衰减
      p.vx *= 0.998;
      p.vy *= 0.998;

      // 生命衰减
      p.alpha *= 0.997;

      // 脉冲亮度
      p.pulse += p.pulseSpeed;
      const pulseVal = Math.sin(p.pulse) * 0.3 + 0.7;

      // 颜色 — 天蓝到蔚蓝渐变
      const isSky = p.hue === 200;
      const color = isSky
        ? `rgba(14, ${Math.floor(165 * pulseVal)}, 233, ${p.alpha * 0.5})`
        : `rgba(${Math.floor(59 * pulseVal)}, ${Math.floor(130 * pulseVal)}, 246, ${p.alpha * 0.45})`;

      this.ctx.beginPath();
      this.ctx.arc(p.x, p.y, p.size * pulseVal, 0, Math.PI * 2);
      this.ctx.fillStyle = color;

      // 发光效果
      if (p.size > 1.5) {
        this.ctx.shadowBlur = 10;
        this.ctx.shadowColor = isSky ? "rgba(14, 165, 233, 0.25)" : "rgba(59, 130, 246, 0.2)";
      }
      this.ctx.fill();
      this.ctx.shadowBlur = 0;

      // 连接线 — 近距离粒子之间
      if (i % 3 === 0) {
        for (let j = i + 1; j < Math.min(i + 6, this.particles.length); j++) {
          const q = this.particles[j];
          if (!q) continue;
          const dx2 = p.x - q.x;
          const dy2 = p.y - q.y;
          const dist2 = Math.sqrt(dx2 * dx2 + dy2 * dy2);
          if (dist2 < 80) {
            this.ctx.beginPath();
            this.ctx.moveTo(p.x, p.y);
            this.ctx.lineTo(q.x, q.y);
            this.ctx.strokeStyle = `rgba(14, 165, 233, ${(1 - dist2 / 80) * 0.06})`;
            this.ctx.lineWidth = 0.5;
            this.ctx.stroke();
          }
        }
      }

      // 淘汰死亡粒子
      if (p.alpha < 0.01 || p.life > p.maxLife * 3 || p.x < -50 || p.x > this.canvas.width + 50 || p.y < -50 || p.y > this.canvas.height + 50) {
        this.particles.splice(i, 1);
      }
    }

    // 补充粒子
    while (this.particles.length < 60) {
      this.particles.push(this._createParticle());
    }

    this.animId = requestAnimationFrame(() => this.animate());
  }

  start() {
    if (this.animId) return;
    this.animate();
  }

  stop() {
    if (this.animId) {
      cancelAnimationFrame(this.animId);
      this.animId = null;
    }
  }
}

// ═════════════════════════════════════════════════════════════════════
// 通用工具
// ═════════════════════════════════════════════════════════════════════

async function api(path, options = {}) {
  const isFormData = options.body instanceof FormData;
  const response = await fetch(path, {
    headers: isFormData ? {} : { "Content-Type": "application/json" },
    credentials: "same-origin",
    ...options,
  });
  const data = await response.json().catch(() => ({ error: "服务器返回了无法解析的响应" }));
  if (!response.ok) {
    if (response.status === 401 && !path.startsWith("/api/auth/")) {
      window.location.reload();
    }
    const error = new Error(data.error || "请求失败");
    error.status = response.status;
    error.code = data.code;
    throw error;
  }
  return data;
}

function evidenceNotice(data) {
  const evidence = data?.evidence;
  if (!evidence?.notice) return "";
  return `<div class="evidence-notice" role="note">
    <strong>使用说明</strong>
    <span>${escapeHtml(evidence.notice)}</span>
  </div>`;
}

function renderDataGovernance() {
  const governance = state.meta?.data_governance;
  if (!governance) return;
  $("#dataNoticeText").textContent = governance.disclaimer || "规划结果仅供参考，请以学校官方信息为准。";
  $("#dataReleaseDate").textContent = governance.release_date ? `数据版本：${governance.release_date}` : "";
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function renderInlineMarkdown(value) {
  let text = escapeHtml(value);
  const safeTokens = [];
  const stash = (html) => {
    const index = safeTokens.push(html) - 1;
    return `\uE000${index}\uE001`;
  };

  text = text.replace(/`([^`\n]+)`/g, (_, code) => stash(`<code>${code}</code>`));
  text = text.replace(
    /\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)/g,
    (_, label, url) => stash(`<a href="${url}" target="_blank" rel="noopener noreferrer">${label}</a>`),
  );
  text = text.replace(
    /(^|[\s（(])(https?:\/\/[^\s<）)，。！？；;]+)/g,
    (_, prefix, url) => `${prefix}${stash(`<a href="${url}" target="_blank" rel="noopener noreferrer">${url}</a>`)}`,
  );
  text = text
    .replace(/\*\*([^*\n]+)\*\*/g, "<strong>$1</strong>")
    .replace(/__([^_\n]+)__/g, "<strong>$1</strong>")
    .replace(/~~([^~\n]+)~~/g, "<del>$1</del>");
  return text.replace(/\uE000(\d+)\uE001/g, (_, index) => safeTokens[Number(index)] || "");
}

function markdownTableCells(line) {
  return line
    .trim()
    .replace(/^\|/, "")
    .replace(/\|$/, "")
    .split("|")
    .map((cell) => cell.trim());
}

function isMarkdownTableSeparator(line) {
  const cells = markdownTableCells(line);
  return cells.length > 0 && cells.every((cell) => /^:?-{3,}:?$/.test(cell.replace(/\s/g, "")));
}

function renderMarkdownSafe(value) {
  const lines = String(value ?? "").replace(/\r\n?/g, "\n").split("\n");
  const output = [];
  let paragraph = [];
  let listType = "";
  let inCodeBlock = false;
  let codeLines = [];

  const closeList = () => {
    if (!listType) return;
    output.push(`</${listType}>`);
    listType = "";
  };
  const flushParagraph = () => {
    if (!paragraph.length) return;
    output.push(`<p>${paragraph.map(renderInlineMarkdown).join("<br>")}</p>`);
    paragraph = [];
  };
  const beforeBlock = () => {
    flushParagraph();
    closeList();
  };

  for (let index = 0; index < lines.length; index++) {
    const line = lines[index];
    const trimmed = line.trim();

    if (/^```/.test(trimmed)) {
      if (inCodeBlock) {
        output.push(`<pre><code>${escapeHtml(codeLines.join("\n"))}</code></pre>`);
        codeLines = [];
        inCodeBlock = false;
      } else {
        beforeBlock();
        inCodeBlock = true;
      }
      continue;
    }
    if (inCodeBlock) {
      codeLines.push(line);
      continue;
    }
    if (!trimmed) {
      beforeBlock();
      continue;
    }

    const nextLine = lines[index + 1] || "";
    if (trimmed.includes("|") && isMarkdownTableSeparator(nextLine)) {
      beforeBlock();
      const headers = markdownTableCells(trimmed);
      const bodyRows = [];
      index += 2;
      while (index < lines.length && lines[index].includes("|") && lines[index].trim()) {
        bodyRows.push(markdownTableCells(lines[index]));
        index++;
      }
      index--;
      output.push(
        `<div class="ai-md-table-wrap"><table class="ai-md-table"><thead><tr>${headers
          .map((cell) => `<th>${renderInlineMarkdown(cell)}</th>`)
          .join("")}</tr></thead><tbody>${bodyRows
          .map(
            (row) =>
              `<tr>${headers
                .map((_, cellIndex) => `<td>${renderInlineMarkdown(row[cellIndex] || "")}</td>`)
                .join("")}</tr>`,
          )
          .join("")}</tbody></table></div>`,
      );
      continue;
    }

    const heading = trimmed.match(/^(#{1,4})\s+(.+)$/);
    if (heading) {
      beforeBlock();
      const level = Math.min(4, heading[1].length + 1);
      output.push(`<h${level}>${renderInlineMarkdown(heading[2])}</h${level}>`);
      continue;
    }
    if (/^(?:-{3,}|\*{3,}|_{3,})$/.test(trimmed)) {
      beforeBlock();
      output.push("<hr>");
      continue;
    }
    const quote = trimmed.match(/^>\s?(.*)$/);
    if (quote) {
      beforeBlock();
      output.push(`<blockquote>${renderInlineMarkdown(quote[1])}</blockquote>`);
      continue;
    }
    const unordered = trimmed.match(/^[-*+]\s+(.+)$/);
    const ordered = trimmed.match(/^\d+[.)]\s+(.+)$/);
    if (unordered || ordered) {
      flushParagraph();
      const wantedType = unordered ? "ul" : "ol";
      if (listType !== wantedType) {
        closeList();
        output.push(`<${wantedType}>`);
        listType = wantedType;
      }
      output.push(`<li>${renderInlineMarkdown((unordered || ordered)[1])}</li>`);
      continue;
    }

    closeList();
    paragraph.push(line);
  }

  if (inCodeBlock) output.push(`<pre><code>${escapeHtml(codeLines.join("\n"))}</code></pre>`);
  flushParagraph();
  closeList();
  return `<div class="ai-md-content">${output.join("")}</div>`;
}

function showToast(message, type = "success") {
  const toast = $("#appToast");
  if (!toast) return;
  toast.textContent = message;
  toast.className = `app-toast ${type}`;
  toast.hidden = false;
  clearTimeout(showToast.timer);
  showToast.timer = setTimeout(() => {
    toast.classList.add("leaving");
    setTimeout(() => {
      toast.hidden = true;
      toast.classList.remove("leaving");
    }, 220);
  }, 2600);
}

function safeFilename(value, fallback = "勤勉导出") {
  const cleaned = String(value || "")
    .replace(/[\\/:*?"<>|]+/g, "_")
    .replace(/\s+/g, " ")
    .trim();
  return cleaned.slice(0, 60) || fallback;
}

function downloadText(filename, text, mimeType = "text/plain;charset=utf-8") {
  const blob = new Blob(["\ufeff", text], { type: mimeType });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 0);
}

function downloadBlob(filename, blob) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 0);
}

async function downloadServerExport({ kind, format, title, data, fallbackFilename }) {
  const response = await fetch("/api/exports", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ kind, format, title, data }),
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(payload.error || `导出失败（HTTP ${response.status}）`);
  }
  const blob = await response.blob();
  const disposition = response.headers.get("Content-Disposition") || "";
  const utf8Match = disposition.match(/filename\*=UTF-8''([^;]+)/i);
  const plainMatch = disposition.match(/filename="?([^";]+)"?/i);
  let filename = fallbackFilename;
  try {
    filename = utf8Match
      ? decodeURIComponent(utf8Match[1])
      : plainMatch
        ? plainMatch[1]
        : fallbackFilename;
  } catch (_) {}
  downloadBlob(filename, blob);
}

function csvCell(value) {
  const text = String(value ?? "");
  return `"${text.replaceAll('"', '""')}"`;
}

function optionList(values, label) {
  return [
    `<option value="">${label}</option>`,
    ...values.map((v) => `<option value="${escapeHtml(v)}">${escapeHtml(v)}</option>`),
  ].join("");
}

function badge(text, type = "") {
  if (!text) return "";
  return `<span class="badge ${type}">${escapeHtml(text)}</span>`;
}

function userStorageKey(name) {
  return `qinmian_${state.user?.id || "guest"}_${name}`;
}

function loadUserPreferences() {
  state.lastTeacherName = localStorage.getItem(userStorageKey("last_teacher")) || "";
  state.persona = localStorage.getItem(userStorageKey("persona")) || "diligent";
  state.studentType = localStorage.getItem(userStorageKey("student_type")) || "domestic";
}

function setAuthMode(mode) {
  const isRegister = mode === "register";
  $$(".auth-tabs [data-auth-mode]").forEach((button) => {
    button.classList.toggle("active", button.dataset.authMode === mode);
  });
  $("#authConfirmRow").hidden = !isRegister;
  $("#authPasswordConfirm").required = isRegister;
  if (!isRegister) $("#authPasswordConfirm").value = "";
  $("#authPassword").autocomplete = isRegister ? "new-password" : "current-password";
  $("#authSubmit").textContent = isRegister ? "创建账号" : "登录";
  $("#authForm").dataset.mode = mode;
  $("#authError").classList.remove("success");
  $("#authError").textContent = "";
}

function initAuthPage() {
  $$(".auth-tabs [data-auth-mode]").forEach((button) => {
    button.addEventListener("click", () => setAuthMode(button.dataset.authMode));
  });
  $("#authForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    const mode = event.currentTarget.dataset.mode || "login";
    const username = $("#authUsername").value.trim();
    const password = $("#authPassword").value;
    const passwordConfirm = $("#authPasswordConfirm").value;
    const submit = $("#authSubmit");
    const errorLine = $("#authError");
    submit.disabled = true;
    errorLine.classList.remove("success");
    errorLine.textContent = "";
    try {
      const payload = { username, password };
      if (mode === "register") payload.password_confirm = passwordConfirm;
      await api(`/api/auth/${mode}`, {
        method: "POST",
        body: JSON.stringify(payload),
      });
      errorLine.classList.add("success");
      errorLine.textContent = mode === "register" ? "注册成功，已为你自动登录。" : "登录成功，正在进入勤勉 AI…";
      submit.textContent = mode === "register" ? "注册成功" : "登录成功";
      await new Promise((resolve) => setTimeout(resolve, 700));
      window.location.reload();
    } catch (error) {
      errorLine.classList.remove("success");
      errorLine.textContent = error.message;
      submit.disabled = false;
    }
  });
  setAuthMode("login");
}

function showAuthPage() {
  const splash = $("#splashScreen");
  if (splash) splash.style.display = "none";
  $("#authOverlay").hidden = false;
  $("#authUsername").focus();
}

async function logout() {
  try {
    await api("/api/auth/logout", { method: "POST", body: "{}" });
  } finally {
    window.location.reload();
  }
}

function initAccountSettings() {
  const overlay = $("#accountSettingsOverlay");
  const message = $("#accountSettingsMessage");
  const close = () => {
    overlay.hidden = true;
    $("#passwordChangeForm").reset();
    $("#deleteAccountPassword").value = "";
    $("#deleteAccountConfirmation").value = "";
    message.textContent = "";
    message.className = "account-settings-message";
  };

  $("#accountSettingsButton").addEventListener("click", () => {
    overlay.hidden = false;
    $("#currentPassword").focus();
  });
  $("#accountSettingsClose").addEventListener("click", close);
  overlay.addEventListener("click", (event) => {
    if (event.target === overlay) close();
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !overlay.hidden) close();
  });

  $("#passwordChangeForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    const button = event.submitter;
    button.disabled = true;
    message.textContent = "正在修改密码…";
    message.className = "account-settings-message";
    try {
      await api("/api/auth/password", {
        method: "POST",
        body: JSON.stringify({
          current_password: $("#currentPassword").value,
          new_password: $("#newPassword").value,
          new_password_confirm: $("#newPasswordConfirm").value,
        }),
      });
      event.currentTarget.reset();
      message.textContent = "密码修改成功，下次登录请使用新密码。";
      message.className = "account-settings-message success";
    } catch (error) {
      message.textContent = error.message;
      message.className = "account-settings-message error";
    } finally {
      button.disabled = false;
    }
  });

  $("#deleteAccountButton").addEventListener("click", async () => {
    const button = $("#deleteAccountButton");
    button.disabled = true;
    message.textContent = "正在核验并删除账号数据…";
    message.className = "account-settings-message";
    try {
      await api("/api/auth/account", {
        method: "DELETE",
        body: JSON.stringify({
          password: $("#deleteAccountPassword").value,
          confirmation: $("#deleteAccountConfirmation").value.trim(),
        }),
      });
      window.location.reload();
    } catch (error) {
      message.textContent = error.message;
      message.className = "account-settings-message error";
      button.disabled = false;
    }
  });
}

// ═════════════════════════════════════════════════════════════════════
// 初始化
// ═════════════════════════════════════════════════════════════════════

async function init() {
  initAuthPage();
  const auth = await api("/api/auth/me");
  if (!auth.authenticated) {
    showAuthPage();
    return;
  }

  state.user = auth.user;
  loadUserPreferences();
  $("#currentUsername").textContent = state.user.username;
  $("#logoutButton").addEventListener("click", logout);
  initLlmSettings();
  initAccountSettings();
  await initAuthenticatedApp();
}

async function initAuthenticatedApp() {
  // 启动粒子系统（在 splash 后面，让 splash 先展示）
  const canvas = $("#particleCanvas");

  state.meta = await api("/api/meta");
  state.llmEnabled = state.meta.llm?.enabled || false;
  state.memoryEnabled = state.meta.knowledge_base?.enabled !== false;
  renderDataGovernance();

  // ── 开场动画处理 ──────────────────────────────────────
  const splash = $("#splashScreen");
  if (splash) {
    // 保留短暂品牌过渡，不再额外制造两秒以上等待
    const minSplashTime = new Promise((r) => setTimeout(r, 650));
    await minSplashTime;

    // 淡出 splash
    splash.classList.add("fade-out");
    setTimeout(() => {
      splash.style.display = "none";
      // splash 消失后再启动粒子，让过渡更干净
      if (canvas) {
        const ps = new ParticleSystem(canvas);
        state.particleSystem = ps;
        ps.start();
      }
    }, 320);
  } else if (canvas) {
    // 无 splash 时直接启动
    const ps = new ParticleSystem(canvas);
    state.particleSystem = ps;
    ps.start();
  }

  // ── 主应用初始化 ──────────────────────────────────────
  updateLlmStatus();

  $("#campusFilter").innerHTML = optionList(state.meta.campuses, "全部校区");
  $("#collegeFilter").innerHTML = optionList(state.meta.colleges, "全部学院");
  $("#disciplineFilter").innerHTML = optionList(state.meta.disciplines, "全部标签");

  ["majorSearch", "campusFilter", "collegeFilter", "disciplineFilter"].forEach((id) => {
    document.getElementById(id).addEventListener("input", () => loadMajors());
  });

  $("#tabs").addEventListener("click", (event) => {
    const button = event.target.closest("button[data-tab]");
    if (!button) return;
    state.activeTab = button.dataset.tab;
    $$("#tabs button").forEach((node) => node.classList.toggle("active", node.dataset.tab === state.activeTab));
    renderTab();
    // 如果在 AI 聊天标签，关闭浮动聊天的 AI 页面标识
  });

  await loadMajors();
  initFloatingChat();
  syncPersonaControls();
  renderFloatingChat();

  // AI 全屏页面初始化
  initAiPage();

  // 开关同步
  syncToggles();

  // 应用已保存的人格主题色
  applyPersonaTheme(state.persona);

  // 打开 AI 页面的按钮
  $("#openAiPage").addEventListener("click", openAiPage);
  $("#openAiPageFromFloat").addEventListener("click", openAiPage);
}

// ═════════════════════════════════════════════════════════════════════
// 开关同步
// ═════════════════════════════════════════════════════════════════════

function syncToggles() {
  const llmChecks = $$("#toggleLLM, #aiToggleLLM");
  const memChecks = $$("#toggleMemory, #aiToggleMemory");
  llmChecks.forEach((el) => { el.checked = state.llmEnabled; });
  memChecks.forEach((el) => { el.checked = state.memoryEnabled; });

  // 添加事件监听（防重复）
  llmChecks.forEach((el) => {
    el.removeEventListener("change", onToggleLLM);
    el.addEventListener("change", onToggleLLM);
  });
  memChecks.forEach((el) => {
    el.removeEventListener("change", onToggleMemory);
    el.addEventListener("change", onToggleMemory);
  });
}

async function onToggleLLM(e) {
  state.llmEnabled = e.target.checked;
  // 同步所有同类型开关
  $$("#toggleLLM, #aiToggleLLM").forEach((el) => { el.checked = state.llmEnabled; });
  try {
    const result = await api("/api/llm/toggle", {
      method: "POST",
      body: JSON.stringify({ enabled: state.llmEnabled }),
    });
    state.llmEnabled = result.enabled;
    state.meta.llm = result;
    $$("#toggleLLM, #aiToggleLLM").forEach((el) => { el.checked = state.llmEnabled; });
  } catch (err) {
    console.warn("LLM toggle failed:", err);
  }
  updateLlmStatus();
}

async function onToggleMemory(e) {
  state.memoryEnabled = e.target.checked;
  $$("#toggleMemory, #aiToggleMemory").forEach((el) => { el.checked = state.memoryEnabled; });
  const statusEl = $("#aiMemoryStatus");
  if (statusEl) statusEl.textContent = state.memoryEnabled ? "开启" : "关闭";
  try {
    const result = await api("/api/knowledge/toggle", {
      method: "POST",
      body: JSON.stringify({ enabled: state.memoryEnabled }),
    });
    state.memoryEnabled = result.enabled;
    if (statusEl) statusEl.textContent = state.memoryEnabled ? "开启" : "关闭";
  } catch (err) {
    state.memoryEnabled = !state.memoryEnabled;
    $$("#toggleMemory, #aiToggleMemory").forEach((el) => { el.checked = state.memoryEnabled; });
    if (statusEl) statusEl.textContent = state.memoryEnabled ? "开启" : "关闭";
    console.warn("Memory toggle failed:", err);
  }
}

// ═════════════════════════════════════════════════════════════════════
// LLM 状态
// ═════════════════════════════════════════════════════════════════════

function updateLlmStatus() {
  const line = $("#llmStatusLine");
  if (!line || !state.meta?.llm) return;
  const persona = currentPersona();
  const personaText = persona ? ` · ${persona.name}` : "";
  if (state.llmEnabled && state.meta.llm.enabled && state.meta.llm.last_error) {
    line.textContent = `大模型最近调用失败 · 点击顶部 API 设置${personaText}`;
    $("#aiModelStatus").textContent = "⚠ API 调用失败";
  } else if (state.llmEnabled && state.meta.llm.enabled) {
    const modelName = state.meta.llm.display_name || `${state.meta.llm.provider} / ${state.meta.llm.model}`;
    line.textContent = `大模型已接入：${modelName}${personaText}`;
    $("#aiModelStatus").textContent = modelName;
  } else {
    line.textContent = `本地工具模式${personaText}`;
    $("#aiModelStatus").textContent = "⚙ 本地模式";
  }
}

// ═════════════════════════════════════════════════════════════════════
// 专业数据
// ═════════════════════════════════════════════════════════════════════

async function loadMajors() {
  const params = new URLSearchParams();
  const q = $("#majorSearch").value.trim();
  const campus = $("#campusFilter").value;
  const college = $("#collegeFilter").value;
  const discipline = $("#disciplineFilter").value;
  if (q) params.set("q", q);
  if (campus) params.set("campus", campus);
  if (college) params.set("college", college);
  if (discipline) params.set("discipline", discipline);
  state.majors = await api(`/api/majors?${params.toString()}`);
  renderMajorList();
  if (!state.selectedMajor || !state.majors.some((major) => major.id === state.selectedMajor.id)) {
    const preferred = state.majors.find((major) => major.name === "人工智能") || state.majors[0];
    if (preferred) await selectMajor(preferred.id);
  }
}

function renderMajorList() {
  $("#majorCount").textContent = `共 ${state.majors.length} 个专业/大类，官方目录总数 ${state.meta.major_count}`;
  $("#majorList").innerHTML = state.majors
    .map(
      (major) => `
        <div class="major-row ${state.selectedMajor?.id === major.id ? "active" : ""}" data-id="${escapeHtml(major.id)}">
          <div class="major-row-title">${escapeHtml(major.display_name)}</div>
          <div class="major-row-meta">${escapeHtml(major.campus)} · ${escapeHtml(major.college)} · ${escapeHtml(major.discipline)}</div>
        </div>`
    )
    .join("");
  $$(".major-row").forEach((node) => {
    node.addEventListener("click", () => selectMajor(node.dataset.id));
  });
}

async function selectMajor(id) {
  const params = new URLSearchParams({ student_type: state.studentType });
  state.curriculum = await api(`/api/curriculum/${encodeURIComponent(id)}?${params.toString()}`);
  state.selectedMajor = state.curriculum.major;
  state.careerRecommendations = null;
  renderMajorHead();
  renderMajorList();
  renderTab();
}

function renderMajorHead() {
  const major = state.selectedMajor;
  if (!major) {
    $("#majorHead").innerHTML = document.getElementById("emptyStateTemplate").innerHTML;
    return;
  }
  const streams = major.streams?.length ? major.streams.map((item) => badge(item, "blue")).join("") : badge("无分流方向", "");
  const related = major.related_colleges?.length ? ` · 计算机相关归类 ${major.related_colleges.join("、")}` : "";
  const studentTypes = [
    { id: "domestic", label: "境内生" },
    { id: "international", label: "境外生" },
  ];
  $("#majorHead").innerHTML = `
    <div class="major-title">
      <h1>${escapeHtml(major.display_name)}</h1>
      ${badge(major.campus, "blue")}
      ${badge(major.first_class_level ? `${major.first_class_level} 一流专业` : "未标注一流层级", major.first_class_level === "G" ? "green" : "")}
      ${major.accredited ? badge("专业认证", "gold") : ""}
      ${major.college_has_doctoral_auth ? badge("学院博士点", "red") : ""}
    </div>
    <div class="muted">官方所属学院 ${escapeHtml(major.college)}${escapeHtml(related)} · 学科标签 ${escapeHtml(major.discipline)} · 学费组 ${escapeHtml(major.tuition_group)}</div>
    <div class="student-type-row">
      <span>毕业学分口径</span>
      <div class="segmented" role="group" aria-label="毕业学分学生类型">
        ${studentTypes.map((item) => `<button type="button" data-student-type="${item.id}" class="${state.studentType === item.id ? "active" : ""}">${item.label}</button>`).join("")}
      </div>
    </div>
    <div class="suggestions">${streams}</div>`;
  $$("[data-student-type]").forEach((button) => {
    button.addEventListener("click", () => setStudentType(button.dataset.studentType));
  });
}

async function setStudentType(studentType, reload = true) {
  state.studentType = studentType === "international" ? "international" : "domestic";
  localStorage.setItem(userStorageKey("student_type"), state.studentType);
  if (reload && state.selectedMajor) {
    await selectMajor(state.selectedMajor.id);
  }
}

async function renderTab() {
  if (!state.curriculum) {
    $("#tabBody").innerHTML = document.getElementById("emptyStateTemplate").innerHTML;
    return;
  }
  const tabHandlers = {
    profile: renderProfile,
    career: renderCareer,
    credits: renderCredits,
    hardness: renderHardness,
    seats: renderSeats,
    conflict: renderConflict,
    professor: renderProfessor,
  };
  const handler = tabHandlers[state.activeTab];
  if (handler) await handler();
}

// ═════════════════════════════════════════════════════════════════════
// 各标签页渲染（沿用原有逻辑，略作样式适配）
// ═════════════════════════════════════════════════════════════════════

async function ensureHot() {
  if (!state.hot) state.hot = await api("/api/hot");
}

async function renderProfile() {
  await ensureHot();
  const rule = state.curriculum.credit_rule;
  const required = state.curriculum.first_required_courses;
  const electives = state.curriculum.recommended_electives;
  const isTemplate = Boolean(rule.is_template);
  const hasSourceConflict = rule.validation?.matches_graduation_total === false;
  const sourceLabel = isTemplate
    ? "当前专业未匹配到真实表格，暂用内置模板"
    : hasSourceConflict
      ? `${rule.student_type_label}真实学分表 · 分类合计 ${rule.validation.category_total} 与总学分 ${rule.graduation_total} 不一致，请复核源表`
      : `${rule.student_type_label}真实学分表 · 匹配专业：${rule.matched_major}`;
  $("#tabBody").innerHTML = `
    <div class="grid-3">
      <div class="stat"><div class="stat-value">${rule.graduation_total}</div><div class="stat-label">${isTemplate ? "毕业总学分模板" : `${escapeHtml(rule.student_type_label)}毕业总学分`}</div></div>
      <div class="stat"><div class="stat-value">${state.curriculum.courses.length}</div><div class="stat-label">已生成课程条目</div></div>
      <div class="stat"><div class="stat-value">${state.selectedMajor.streams.length || 1}</div><div class="stat-label">分流/方向数量</div></div>
    </div>
    <div class="data-source-note ${isTemplate || hasSourceConflict ? "warning" : "verified"}">${escapeHtml(sourceLabel)}</div>
    <div class="grid-2">
      <section class="panel"><h2>毕业学分类别</h2><table class="table"><thead><tr><th>类别</th><th>要求学分</th></tr></thead><tbody>
        ${Object.entries(rule.categories).map(([name, credits]) => `<tr><td>${escapeHtml(name)}</td><td>${escapeHtml(credits ?? "-")}</td></tr>`).join("")}
      </tbody></table></section>
      <section class="panel"><h2>当前热门5个方向</h2><div class="hot-list">
        ${state.hot.map((item) => `<div class="result-item"><div class="course-title">${item.rank}. ${escapeHtml(item.name)}</div><div class="course-meta">${escapeHtml(item.why)}</div></div>`).join("")}
      </div></section>
    </div>
    <div class="grid-2">
      <section class="panel"><h2>首选专业必修课</h2>${courseList(required)}</section>
      <section class="panel"><h2>建议选修课</h2>${courseList(electives)}</section>
    </div>`;
}

function courseList(courses) {
  if (!courses.length) return `<div class="empty-state">暂无课程数据</div>`;
  return `<div class="course-list">${courses.map((course) => {
    const teachers = course.teachers?.length ? course.teachers.map((t) => t.name).join("、") : "待导入任课教师";
    return `<div class="course-item"><div class="course-title">${escapeHtml(course.name)} ${badge(`${course.credits}学分`)}</div><div class="course-meta">第${course.semester || "-"}学期 · ${escapeHtml(course.category)} · 任课：${escapeHtml(teachers)}</div></div>`;
  }).join("")}</div>`;
}

// ── 职业规划 ──────────────────────────────────────────────────────

async function ensureCareerProfiles() {
  if (!state.careerProfiles) state.careerProfiles = await api("/api/careers");
}

async function ensureCareerRecommendations() {
  const majorId = state.selectedMajor?.id;
  if (!majorId) return;
  if (state.careerRecommendations?.major?.id === majorId) return;
  state.careerRecommendations = await api(
    `/api/careers/recommendations?major_id=${encodeURIComponent(majorId)}&limit=6`
  );
}

function renderMajorCareerRecommendations() {
  const data = state.careerRecommendations;
  const rows = data?.recommendations || [];
  if (!rows.length) {
    return `<div class="empty-state">当前专业暂未匹配到职业画像，请从完整职业库中搜索。</div>`;
  }
  return `
    <div class="major-career-heading">
      <div>
        <strong>${escapeHtml(data.major.display_name)}适配职业画像</strong>
        <span>先选职业，再生成对应的分学期学习路线</span>
      </div>
      <span class="major-career-count">推荐 ${rows.length} 个方向</span>
    </div>
    <div class="major-career-recommendations">
      ${rows.map((role, index) => `
        <button type="button" class="major-career-card ${index === 0 ? "primary-match" : ""}"
                data-recommended-career="${escapeHtml(role.name)}">
          <span class="major-career-rank">${index + 1}</span>
          <span class="major-career-content">
            <span class="major-career-title">
              <strong>${escapeHtml(role.name)}</strong>
              <em>${role.score}% · ${escapeHtml(role.level)}</em>
            </span>
            <span class="major-career-meta">${escapeHtml(role.category)} · ${escapeHtml(role.reason)}</span>
            ${role.description ? `<span class="major-career-description">${escapeHtml(role.description)}</span>` : ""}
          </span>
        </button>
      `).join("")}
    </div>
    <p class="career-library-notice">${escapeHtml(data.notice || "")}</p>`;
}

function renderCareerRoleSuggestions() {
  const container = $("#careerRoleSuggestions");
  if (!container || !state.careerProfiles) return;
  const category = $("#careerCategory")?.value || "";
  const roles = state.careerProfiles.roles
    .filter((role) => !category || role.category === category)
    .slice(0, 12);
  container.innerHTML = roles.map((role) => `
    <button type="button" class="career-role-chip" data-career-role="${escapeHtml(role.name)}">
      <strong>${escapeHtml(role.name)}</strong>
      <span>${escapeHtml(role.category)}</span>
    </button>
  `).join("");
  container.querySelectorAll("[data-career-role]").forEach((button) => {
    button.addEventListener("click", () => {
      $("#careerInput").value = button.dataset.careerRole;
      generateCareerPlan();
    });
  });
}

async function renderCareer() {
  await Promise.all([
    ensureCareerProfiles(),
    ensureCareerRecommendations(),
  ]);
  const library = state.careerProfiles;
  const recommendedRoles = state.careerRecommendations?.recommendations || [];
  const defaultCareer = recommendedRoles[0]?.name || "";
  const categoryOptions = library.categories
    .map((item) => `<option value="${escapeHtml(item.name)}">${escapeHtml(item.name)}（${item.count}）</option>`)
    .join("");
  const roleOptions = library.roles.flatMap((role) => [
    `<option value="${escapeHtml(role.name)}">${escapeHtml(role.category)}</option>`,
    ...role.aliases.map((alias) => (
      `<option value="${escapeHtml(alias)}">${escapeHtml(alias)} → ${escapeHtml(role.name)}</option>`
    )),
  ]).join("");
  $("#tabBody").innerHTML = `
    <section class="panel"><h2>未来职业画像与专业适配课表</h2>
      ${renderMajorCareerRecommendations()}
    </section>
    <section class="panel"><h2>生成所选职业的专业适配课表</h2>
      <div class="career-library-summary">
        已收录 <strong>${library.count}</strong> 个职业画像。上方是根据当前专业自动推荐的方向，也可以在这里搜索其他岗位。
      </div>
      <div class="actions">
      <label><span>职业分类</span><select id="careerCategory"><option value="">全部方向</option>${categoryOptions}</select></label>
      <label><span>理想岗位</span><input id="careerInput" list="careerRoleOptions" value="${escapeHtml(defaultCareer)}" placeholder="先选上方推荐职业，或搜索其他岗位" /></label>
      <datalist id="careerRoleOptions">${roleOptions}</datalist>
      <button class="primary" id="careerBtn">生成课表</button>
      <div class="export-control">
        <select id="careerExportFormat" class="export-format">
          <option value="csv">CSV</option>
          <option value="docx">DOCX</option>
          <option value="pdf">PDF</option>
          <option value="xls">XLS</option>
        </select>
        <button id="careerExportBtn" disabled>⇩ 导出课表</button>
      </div>
      </div>
      <div class="career-role-suggestions" id="careerRoleSuggestions"></div>
      <p class="career-library-notice">${escapeHtml(library.notice || "")}</p>
    </section>
    <section class="panel" id="careerResult"><div class="empty-state">输入岗位后生成路线。</div></section>`;
  $("#careerBtn").addEventListener("click", () => generateCareerPlan());
  $("#careerExportBtn").addEventListener("click", exportCareerPlan);
  $("#careerCategory").addEventListener("change", renderCareerRoleSuggestions);
  $("#careerInput").addEventListener("keydown", (event) => {
    if (event.key === "Enter") generateCareerPlan();
  });
  $$("[data-recommended-career]").forEach((button) => {
    button.addEventListener("click", () => {
      generateCareerPlan(button.dataset.recommendedCareer);
    });
  });
  renderCareerRoleSuggestions();
  if (defaultCareer) generateCareerPlan(defaultCareer);
}

async function generateCareerPlan(careerOverride = "") {
  const input = $("#careerInput");
  const career = String(careerOverride || input?.value || "").trim();
  if (!career) {
    showToast("请先选择或输入一个职业画像。", "error");
    return;
  }
  if (input) input.value = career;
  const data = await api("/api/plan", { method: "POST", body: JSON.stringify({ career, major_id: state.selectedMajor.id }) });
  state.careerPlan = data;
  $("#careerResult").innerHTML = renderTimetableFromPlan(data);
  $("#careerExportBtn").disabled = false;
}

function renderTimetableFromPlan(data) {
  const roleName = escapeHtml(data.matched_role || "目标岗位");
  const majorName = escapeHtml(data.selected_major?.display_name || "");
  const salary = data.salary_range || "";
  const match = data.career_match || {};
  const planningPeriods = data.planning_periods?.length ? data.planning_periods : (data.semesters || []);
  const academicYears = data.academic_years?.length
    ? data.academic_years.map((year) => ({
        ...year,
        periods: year.periods?.length
          ? year.periods
          : (year.period_indexes || [])
              .map((periodIndex) => planningPeriods.find((period) => period.period_index === periodIndex))
              .filter(Boolean),
      }))
    : [{ year: 1, label: "学习路线", periods: planningPeriods }];
  const firstPeriods = academicYears[0]?.periods || [];
  let html = `<div class="career-overview">`;
  html += `<span class="career-overview-item">🎯 岗位：<strong>${roleName}</strong></span>`;
  html += `<span class="career-overview-item">🏛 专业：<strong>${majorName}</strong></span>`;
  html += `<span class="career-overview-item">📚 ${data.program_years || academicYears.length} 学年 · ${data.planning_period_count || planningPeriods.length} 个规划阶段</span>`;
  html += `<span class="career-overview-item">🏫 ${data.regular_semester_count || data.semester_count || 0} 个正式学期 + ${data.summer_term_count || 0} 个小学期</span>`;
  if (salary) html += `<span class="career-overview-item">💰 薪资参考：<strong>${salary}</strong></span>`;
  html += `</div>`;
  if (data.profile_description) {
    html += `<p class="career-profile-description"><strong>${escapeHtml(data.profile_category || "职业方向")}：</strong>${escapeHtml(data.profile_description)}</p>`;
  }
  if (match.notice) {
    const matchTone = match.is_custom ? "custom" : (match.type === "semantic" ? "semantic" : "matched");
    html += `<div class="career-match-note ${matchTone}">${escapeHtml(match.notice)}${data.available_profile_count ? ` 当前职业库共 ${data.available_profile_count} 个画像。` : ""}</div>`;
  }
  html += evidenceNotice(data);
  const fit = data.selected_major_fit || {};
  const fitScore = Number(fit.score || 0);
  const fitTone = fitScore >= 75 ? "high" : fitScore >= 50 ? "medium" : fitScore >= 30 ? "transfer" : "low";
  html += `<section class="career-fit-card ${fitTone}">
    <div class="career-fit-heading">
      <strong>职业—专业匹配判断</strong>
      <span class="career-fit-score">${fitScore}% · ${escapeHtml(fit.level || "待评估")}</span>
    </div>
    <p>${escapeHtml(fit.reason || "正在根据专业培养方案评估。")}</p>
    ${fit.missing_core_courses?.length ? `<div class="career-fit-gap"><strong>建议补齐：</strong>${fit.missing_core_courses.map(escapeHtml).join("、")}</div>` : ""}
  </section>`;
  if (data.recommended_majors?.length) {
    html += `<div class="career-recommended"><strong>更匹配的专业参考：</strong>${data.recommended_majors.slice(0, 5).map((row) => {
      const percent = Math.round(Number(row.score || 0) * 100);
      return `<span>${escapeHtml(row.major?.display_name || "")} ${percent}%</span>`;
    }).join("")}</div>`;
  }
  html += `<div class="semester-tabs academic-year-tabs" id="careerYearTabs">`;
  for (let i = 0; i < academicYears.length; i++) {
    const year = academicYears[i];
    html += `<button class="semester-tab${i === 0 ? " active" : ""}" data-year-index="${i}">${escapeHtml(year.label)}</button>`;
  }
  html += `</div>`;
  html += `<div class="semester-tabs career-term-tabs" id="careerTermTabs">`;
  for (let i = 0; i < firstPeriods.length; i++) {
    const period = firstPeriods[i];
    html += `<button class="semester-tab${i === 0 ? " active" : ""}${period.term_type === "summer" ? " summer" : ""}" data-period-index="${i}">${escapeHtml(period.short_label || period.label)}</button>`;
  }
  html += `</div>`;
  html += `<div id="semesterTimetable">`;
  if (firstPeriods.length > 0) {
    html += renderSingleSemesterView(firstPeriods[0]);
  }
  html += `</div>`;
  html += `<div class="career-plan-details">`;
  if (data.must_courses && data.must_courses.length > 0) {
    html += `<div class="career-core-courses"><strong>核心课程：</strong>`;
    for (const n of data.must_courses) {
      html += `<span>${escapeHtml(n)}</span>`;
    }
    html += `</div>`;
  }
  if (data.milestones && data.milestones.length > 0) {
    html += `<div class="career-milestones"><strong>📌 路线建议：</strong>`;
    for (const m of data.milestones) {
      html += `<div>· ${escapeHtml(m)}</div>`;
    }
    html += `</div>`;
  }
  if (data.planning_note) html += `<p class="career-planning-note">说明：${escapeHtml(data.planning_note)}</p>`;
  html += `</div>`;
  setTimeout(() => {
    const yearTabs = document.querySelectorAll("#careerYearTabs .semester-tab");
    const termContainer = document.getElementById("careerTermTabs");
    const timetable = document.getElementById("semesterTimetable");

    const bindTermTabs = (periods) => {
      const termTabs = document.querySelectorAll("#careerTermTabs .semester-tab");
      for (const tab of termTabs) {
        tab.addEventListener("click", function() {
          termTabs.forEach(t => t.classList.remove("active"));
          this.classList.add("active");
          const period = periods[parseInt(this.dataset.periodIndex, 10)];
          if (period && timetable) timetable.innerHTML = renderSingleSemesterView(period);
        });
      }
    };

    const renderYear = (yearIndex) => {
      const periods = academicYears[yearIndex]?.periods || [];
      if (termContainer) {
        termContainer.innerHTML = periods.map((period, index) =>
          `<button class="semester-tab${index === 0 ? " active" : ""}${period.term_type === "summer" ? " summer" : ""}" data-period-index="${index}">${escapeHtml(period.short_label || period.label)}</button>`
        ).join("");
      }
      if (timetable) {
        timetable.innerHTML = periods.length
          ? renderSingleSemesterView(periods[0])
          : `<div class="empty-state">该学年暂无规划数据。</div>`;
      }
      bindTermTabs(periods);
    };

    for (const tab of yearTabs) {
      tab.addEventListener("click", function() {
        yearTabs.forEach(t => t.classList.remove("active"));
        this.classList.add("active");
        renderYear(parseInt(this.dataset.yearIndex, 10));
      });
    }
    bindTermTabs(firstPeriods);
  }, 0);
  return html;
}

function renderSingleSemesterView(sem) {
  const days = ["周一", "周二", "周三", "周四", "周五"];
  const timeslots = ["08:00-09:40", "10:00-11:40", "14:30-16:10", "16:20-18:00", "19:00-20:40"];
  let html = `<div class="timetable-container">`;
  const composition = sem.suggested_course_count
    ? ` · ${sem.official_course_count || 0} 门培养方案课程 + ${sem.suggested_course_count} 项规划建议`
    : "";
  const periodType = sem.term_type === "summer" ? " · 小学期规划（非正式课程）" : "";
  html += `<div class="timetable-header"><h3>📅 ${escapeHtml(sem.label)}</h3><span class="credits-badge">${sem.credits} 学分${composition}${periodType} · ${escapeHtml(sem.focus || "")}</span></div>`;
  html += `<div class="timetable-week-grid">`;
  html += `<div class="timetable-day-header">时间</div>`;
  for (const d of days) html += `<div class="timetable-day-header">${d}</div>`;
  const dayAssign = {};
  const cats = sem.courses || [];
  let ci = 0;
  for (const c of cats) {
    const da = (ci % 5) + 1;
    const ts = Math.floor(ci / 5) % 5;
    ci++;
    const key = da + "-" + ts;
    if (!dayAssign[key]) dayAssign[key] = [];
    dayAssign[key].push(c);
  }
  let idx = 0;
  for (const ts of timeslots) {
    html += `<div class="timetable-time-label">${ts}</div>`;
    for (let d = 1; d <= 5; d++) {
      const key = d + "-" + idx;
      const courseList = dayAssign[key] || [];
      html += `<div>`;
      for (const c of courseList) {
        const cat = c.category || "";
        let typeClass = "type-required";
        let badgeCls = "badge-required";
        if (c.origin === "career") { typeClass = "type-career"; badgeCls = "badge-career"; }
        else if (cat.includes("选修") || c.origin === "elective") { typeClass = "type-elective"; badgeCls = "badge-elective"; }
        else if (cat.includes("通识") || c.origin === "general_elective") { typeClass = "type-general"; badgeCls = "badge-general"; }
        else if (cat.includes("实践")) { typeClass = "type-practice"; badgeCls = "badge-practice"; }
        const note = c.planning_note ? ` title="${escapeHtml(c.planning_note)}"` : "";
        html += `<div class="course-card ${typeClass}"${note}><span class="course-name">${escapeHtml(c.name)}</span>`;
        html += `<span class="course-category ${badgeCls}">${escapeHtml(cat || "")}</span>`;
        html += `</div>`;
      }
      html += `</div>`;
    }
    idx++;
  }
  html += `</div></div>`;
  if (cats.length > 0) {
    html += `<div class="semester-course-summary">`;
    for (const c of cats) {
      html += `<span class="${c.origin === "career" ? "suggested" : ""}">${escapeHtml(c.name)}<small>${c.origin === "career" ? "规划建议" : `${c.credits}学分`}</small></span>`;
    }
    html += `</div>`;
  }
  return html;
}

async function exportCareerPlan() {
  const data = state.careerPlan;
  if (!data?.semesters?.length) {
    showToast("请先生成职业课表。", "error");
    return;
  }
  const format = $("#careerExportFormat")?.value || "csv";
  const rows = [
    ["目标岗位", "当前专业", "匹配度", "匹配结论", "学年", "学期/阶段", "课程/建议", "类别", "学分", "来源", "说明"],
  ];
  const periods = data.planning_periods?.length ? data.planning_periods : data.semesters;
  for (const period of periods) {
    for (const course of period.courses || []) {
      rows.push([
        data.matched_role || data.career || "",
        data.selected_major?.display_name || "",
        `${data.selected_major_fit?.score || 0}%`,
        data.selected_major_fit?.level || "",
        period.year_label || "",
        period.short_label || period.label,
        course.name || "",
        course.category || "",
        course.credits ?? 0,
        period.term_type === "summer" ? "小学期职业规划建议" : (course.origin === "career" ? "职业规划建议" : "培养方案"),
        course.planning_note || "",
      ]);
    }
  }
  const title = `${safeFilename(data.selected_major?.display_name)}_${safeFilename(data.matched_role)}`;
  if (format === "csv") {
    const csv = rows.map((row) => row.map(csvCell).join(",")).join("\r\n");
    downloadText(`${title}_职业课表.csv`, csv, "text/csv;charset=utf-8");
    showToast("课表已导出为 CSV，可用 Excel 打开。");
    return;
  }
  const button = $("#careerExportBtn");
  button.disabled = true;
  try {
    await downloadServerExport({
      kind: "career_plan",
      format,
      title,
      data,
      fallbackFilename: `${title}_职业课表.${format}`,
    });
    showToast(`课表已导出为 ${format.toUpperCase()}。`);
  } catch (error) {
    showToast(error.message, "error");
  } finally {
    button.disabled = false;
  }
}

// ── 学分体检 ──────────────────────────────────────────────────────

function renderCredits() {
  // Load colleges for the cascade selector
  const allColleges = state.meta?.colleges || [];
  const currentCollege = state.creditCollege || "";
  const currentMajor = state.creditMajor || state.selectedMajor?.id || "";
  const majors = currentCollege ? (state.creditMajorsCache?.[currentCollege] || []) : [];
  const courses = state.creditCourses || [];
  const completedText = state.creditCompletedText || "思想道德与法治\n大学英语\n程序设计基础\n数据结构";

  $("#tabBody").innerHTML = `
    <section class="panel"><h2>学分体检与毕业风险预警</h2>
      <div class="actions" style="flex-wrap:wrap">
        <label><span>选择学院</span><select id="creditCollege"><option value="">-- 请选择学院 --</option>${allColleges.map(c => `<option value="${escapeHtml(c)}"${c === currentCollege ? " selected" : ""}>${escapeHtml(c)}</option>`).join("")}</select></label>
        <label><span>选择专业</span><select id="creditMajor"><option value="">-- 请选择专业 --</option>${majors.map(m => `<option value="${escapeHtml(m.id)}"${m.id === currentMajor ? " selected" : ""}>${escapeHtml(m.display_name || m.name)}</option>`).join("")}</select></label>
        <label><span>培养方案课程（点击添加）</span><div id="creditCourseTags" style="max-height:120px;overflow-y:auto;border:1px solid #ddd;border-radius:6px;padding:6px;display:flex;flex-wrap:wrap;gap:4px">${courses.map(c => `<span class="tag-btn" data-course="${escapeHtml(c.name)}">${escapeHtml(c.name)}</span>`).join("")}</div></label>
      </div>
      <div class="actions">
        <label><span>已修课程，每行一门</span><textarea id="completedCourses">${escapeHtml(completedText)}</textarea></label>
        <button class="primary" id="creditBtn">开始体检</button>
      </div>
    </section>
    <section class="panel" id="creditResult"><div class="empty-state">选择专业并输入已修课程后查看缺口。</div></section>`;
  
  $("#creditCollege").addEventListener("change", async () => {
    state.creditCollege = $("#creditCollege").value;
    state.creditMajor = "";
    state.creditCourses = [];
    if (!state.creditMajorsCache) state.creditMajorsCache = {};
    if (state.creditCollege && !state.creditMajorsCache[state.creditCollege]) {
      const data = await api(`/api/majors?college=${encodeURIComponent(state.creditCollege)}`);
      state.creditMajorsCache[state.creditCollege] = data;
    }
    renderCredits();
  });
  $("#creditMajor").addEventListener("change", async () => {
    state.creditMajor = $("#creditMajor").value;
    state.creditCourses = [];
    if (state.creditMajor) {
      const data = await api(`/api/curriculum/${state.creditMajor}?student_type=${state.studentType}`);
      state.creditCourses = data.courses || [];
      state.creditSelectedMajor = data.major;
    }
    renderCredits();
  });
  // Delegate click on tag buttons
  setTimeout(() => {
    $$(".tag-btn").forEach(el => {
      el.addEventListener("click", () => {
        const courseName = el.dataset.course;
        const ta = $("#completedCourses");
        const existing = ta.value.split(/\n/).map(s => s.trim()).filter(Boolean);
        if (!existing.includes(courseName)) {
          ta.value = [...existing, courseName].join("\n");
        }
      });
    });
  }, 50);
  $("#creditBtn").addEventListener("click", runCreditCheck);
}

async function runCreditCheck() {
  const majorId = state.creditMajor || state.selectedMajor?.id;
  if (!majorId) { $("#creditResult").innerHTML = `<div class="empty-state">请先在学分体检页面顶部选择一个专业。</div>`; return; }
  const completed = $("#completedCourses").value.split(/\n|,|，/).map((item) => item.trim()).filter(Boolean);
  state.creditCompletedText = completed.join("\n");
  const data = await api("/api/credits/check", { method: "POST", body: JSON.stringify({ major_id: majorId, completed_courses: completed, student_type: state.studentType }) });
  $("#creditResult").innerHTML = `
    <h2>${escapeHtml(data.major.display_name)} · 已修 ${data.total_earned} / ${data.graduation_total} 学分</h2>
    <div class="grid-2"><div><h3>分类缺口</h3><table class="table"><thead><tr><th>类别</th><th>已修</th><th>要求</th><th>缺口</th></tr></thead><tbody>
      ${data.deficits.map((row) => `<tr><td>${escapeHtml(row.category)}</td><td>${row.earned}</td><td>${escapeHtml(row.required ?? "-")}</td><td>${row.gap === null ? `<span class="badge gold">需确认</span>` : row.gap > 0 ? `<span class="badge red">${row.gap}</span>` : `<span class="badge green">OK</span>`}</td></tr>`).join("")}
    </tbody></table></div><div><h3>识别结果</h3><div class="result-list">
      ${data.matched.map((item) => `<div class="result-item">${escapeHtml(item.name)} · ${escapeHtml(item.category)} · ${item.credits}学分</div>`).join("") || `<div class="empty-state">没有匹配到课程</div>`}
      ${data.unmatched.map((name) => `<div class="result-item">未识别：${escapeHtml(name)}</div>`).join("")}
    </div></div></div>`;
}

// ── 课程硬核 ──────────────────────────────────────────────────────

function renderHardness() {
  const defaultCourse = state.curriculum?.first_required_courses?.[0]?.name || "数据结构";
  $("#tabBody").innerHTML = `
    <section class="panel"><h2>课程难度多维分析 · 星级评定</h2><p class="muted">基于教务系统全量数据 + 论坛评价，多维度计算课程难度星级</p>
      <div class="actions"><label><span>课程名称</span><input id="hardCourse" value="${escapeHtml(defaultCourse)}" /></label><button class="primary" id="hardBtn">分析课程</button></div>
    </section>
    <section class="panel" id="hardResult"><div class="empty-state">输入课程名称后自动分析。</div></section>`;
  $("#hardBtn").addEventListener("click", runHardness);
}

async function runHardness() {
  const course = $("#hardCourse").value.trim() || "数据结构";
  const data = await api("/api/course/analyze", { method: "POST", body: JSON.stringify({ course }) });
  const stars = data.stars;
  let starHtml = "";
  if (stars && stars > 0) {
    starHtml = `<div class="difficulty-stars"><span class="star-display">${"⭐".repeat(stars)}${"☆".repeat(5 - stars)}</span>
      <span class="star-label ${stars >= 4 ? 'hard' : stars <= 2 ? 'easy' : 'medium'}">${escapeHtml(data.star_label || "")}</span>
      <span class="star-score">综合难度 ${data.difficulty_score}/100</span></div>
      <div class="dimensions">${data.dimensions ? Object.entries(data.dimensions).map(([key, val]) => {
        const labels = { credit_intensity: "学分强度", category_difficulty: "课程类别", knowledge_complexity: "知识复杂度", specialization: "专业化程度", teaching_intensity: "教学强度", review_score: "评价反馈" };
        return metricBar(labels[key] || key, val, val >= 65 ? "risk" : val >= 45 ? "warn" : "");
      }).join("") : ""}</div>`;
  }
  const legacyHtml = (data.hardcore_index != null) ? `<h3>传统指标</h3>${data.workload != null ? metricBar("作业量", data.workload, "risk") : ""}${data.grading_friendliness != null ? metricBar("给分友好度", data.grading_friendliness, "warn") : ""}${data.substance != null ? metricBar("干货程度", data.substance, "") : ""}` : "";
  $("#hardResult").innerHTML = `<h2>${escapeHtml(data.course)}</h2>${starHtml}${legacyHtml}<p class="muted">${escapeHtml(data.summary || "")}</p>
    ${data.evidence?.length ? `<h3>评价证据 (${data.evidence.length}条)</h3><div class="result-list">${data.evidence.map((item) => `<div class="result-item">${escapeHtml(item.text)}</div>`).join("")}</div>` : ""}
    ${data.meta ? `<div class="meta-info"><small>学分 ${data.meta.avg_credits} · 教师 ${data.meta.unique_teachers}人 · 面向 ${data.meta.unique_majors} 个专业 · ${data.meta.review_count}条评价</small></div>` : ""}`;
}

function metricBar(label, value, type) {
  return `<div class="course-item"><div class="course-title">${escapeHtml(label)} · ${value}/100</div><div class="bar ${type}"><span style="width:${value}%"></span></div></div>`;
}

// ── 抢课监控 ──────────────────────────────────────────────────────

async function renderSeats() {
  $("#tabBody").innerHTML = `
    <section class="panel"><h2>抢课余位实时监控与自动捡漏</h2><div class="actions">
      <label><span>目标课程</span><input id="seatCourse" value="机器学习" /></label><button class="primary" id="watchBtn">加入监控</button>
      <button id="tickBtn">模拟释放名额</button>
    </div></section>
    <section class="panel" id="seatResult"></section>`;
  $("#watchBtn").addEventListener("click", watchCourse);
  $("#tickBtn").addEventListener("click", tickSeats);
  await refreshSeats();
}

async function refreshSeats() {
  const data = await api("/api/seats");
  $("#seatResult").innerHTML = seatHtml(data);
}

async function watchCourse() {
  const course = $("#seatCourse").value.trim() || "机器学习";
  await api("/api/seats/watch", { method: "POST", body: JSON.stringify({ course }) });
  await refreshSeats();
}

async function tickSeats() {
  const data = await api("/api/seats/tick", { method: "POST", body: "{}" });
  $("#seatResult").innerHTML = seatHtml(data);
}

function seatHtml(data) {
  const offerings = data.offerings || [];
  return `<h2>模拟教务余位 <span class="simulation-badge">演示数据</span></h2>${evidenceNotice(data)}<table class="table"><thead><tr><th>课程</th><th>教师</th><th>时间</th><th>容量</th><th>余位</th></tr></thead><tbody>
    ${offerings.map((item) => `<tr><td>${escapeHtml(item.course)}-${escapeHtml(item.section)}</td><td>${escapeHtml(item.teacher)}</td><td>${escapeHtml(item.day)} ${escapeHtml(item.start)}-${escapeHtml(item.end)}</td><td>${item.enrolled}/${item.capacity}</td><td>${item.remaining > 0 ? `<span class="badge green">${item.remaining}</span>` : `<span class="badge red">满员</span>`}</td></tr>`).join("")}
  </tbody></table><h3>监控事件</h3><div class="result-list">${(data.events || []).map((e) => `<div class="result-item">${escapeHtml(e.time)} · ${escapeHtml(e.message)}</div>`).join("") || `<div class="empty-state">暂无事件</div>`}</div>`;
}

// ── 冲突微调 ──────────────────────────────────────────────────────

function renderConflict() {
  if (!state.conflictCourses) {
    state.conflictCourses = [
      { name: "数据结构", dayNum: 2, startTime: "08:00", endTime: "09:40", category: "专业必修" },
      { name: "大学英语", dayNum: 2, startTime: "10:00", endTime: "11:40", category: "通识必修" },
      { name: "机器学习", dayNum: 4, startTime: "14:30", endTime: "16:10", category: "专业选修" }
    ];
  }
  const pool = [...new Set((state.curriculum?.courses || []).map(c => c.name))];
  const days = ["周一","周二","周三","周四","周五"];
  let html = `<section class="panel"><h2>课程冲突智能微调器</h2>
    <p class="muted">上传课表截图或文件自动识别，也可以手动添加课程。冲突课程会红色高亮。</p>
    <div class="actions" style="gap:6px;flex-wrap:wrap">
      <input type="file" id="conflictFileInput" accept="image/*,.pdf,.docx,.xlsx,.xlsm,.csv,.txt,.json" style="display:none" />
      <button class="primary" id="conflictUploadBtn" style="font-size:12px">上传课表图片/文件</button>
      <span style="font-size:11px;color:#64748b">或手动添加课程</span>
    </div>
    <div id="conflictCourseList" style="margin-bottom:10px"></div>
    <div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:10px">
      <button class="primary" id="addCourseBtn">+ 添加课程</button>
      <button class="primary" id="checkConflictBtn">检查冲突</button>
    </div>
    <div class="course-pool" id="coursePool">
      <span style="color:#64748b;font-size:11px">课程池（点击添加）：</span>
      ${pool.slice(0, 20).map(n => `<span class="pool-item" data-name="${escapeHtml(n)}">${escapeHtml(n)}</span>`).join("")}
    </div>
    </section>
    <section class="panel" id="conflictResult"><div class="empty-state">添加课程后点击检查冲突，或上传课表图片自动导入。</div></section>`;
  $("#tabBody").innerHTML = html;
  renderConflictCourseInputs();
  $("#addCourseBtn").addEventListener("click", addConflictCourse);
  $("#checkConflictBtn").addEventListener("click", runConflict);
  // u2192 Upload timetable image
  const conflictUploadBtn = $("#conflictUploadBtn");
  const conflictFileInput = $("#conflictFileInput");
  if (conflictUploadBtn && conflictFileInput) {
    conflictUploadBtn.addEventListener("click", () => conflictFileInput.click());
    conflictFileInput.addEventListener("change", handleConflictFileUpload);
  }
  setTimeout(() => {
    document.querySelectorAll("#coursePool .pool-item").forEach(el => {
      el.addEventListener("click", () => {
        const name = el.dataset.name;
        if (state.conflictCourses.find(c => c.name === name)) return;
        const slots = [
          [1, "08:00", "09:40"], [1, "10:00", "11:40"],
          [2, "08:00", "09:40"], [2, "10:00", "11:40"],
          [3, "14:30", "16:10"], [4, "14:30", "16:10"],
          [5, "16:20", "18:00"],
        ];
        const used = new Set(state.conflictCourses.map(c => `${c.dayNum}-${c.startTime}-${c.endTime}`));
        const slot = slots.find(([day, start, end]) => !used.has(`${day}-${start}-${end}`)) || slots[0];
        state.conflictCourses.push({ name, dayNum: slot[0], startTime: slot[1], endTime: slot[2], category: "专业选修" });
        renderConflict();
      });
    });
  }, 0);
}

function renderConflictCourseInputs() {
  const container = $("#conflictCourseList");
  if (!container) return;
  const days = ["周一","周二","周三","周四","周五"];
  const cats = ["专业必修","专业选修","通识必修","通识选修","实践与创新"];
  let html = `<div class="conflict-input-grid">`;
  for (let i = 0; i < (state.conflictCourses || []).length; i++) {
    const c = state.conflictCourses[i];
    html += `<div class="conflict-input-course">
      <span style="font-weight:600;color:#0f172a;min-width:60px">${escapeHtml(c.name)}</span>
      <select onchange="state.conflictCourses[${i}].dayNum=parseInt(this.value);">
        ${days.map((d, idx) => `<option value="${idx+1}"${c.dayNum === idx+1 ? " selected" : ""}>${d}</option>`).join("")}
      </select>
      <input type="time" value="${c.startTime}" onchange="state.conflictCourses[${i}].startTime=this.value;" style="width:80px">
      <input type="time" value="${c.endTime}" onchange="state.conflictCourses[${i}].endTime=this.value;" style="width:80px">
      <select onchange="state.conflictCourses[${i}].category=this.value;">
        ${cats.map(cat => `<option value="${cat}"${c.category === cat ? " selected" : ""}>${cat}</option>`).join("")}
      </select>
      <span class="remove-course" onclick="removeConflictCourse(${i})">x</span>
    </div>`;
  }
  html += `</div>`;
  container.innerHTML = html;
}

async function runConflict() {
  const rawCourses = state.conflictCourses || [];
  // Normalize field names: backend expects day/start/end (strings)
  const courses = rawCourses.map(c => ({
    name: c.name,
    day: ({1:"周一",2:"周二",3:"周三",4:"周四",5:"周五"})[c.dayNum] || c.day || "",
    start: c.startTime || c.start || "08:00",
    end: c.endTime || c.end || "09:40",
    category: c.category || "专业必修",
    semester: c.semester || 3
  }));
  const data = await api("/api/conflicts", { method: "POST", body: JSON.stringify({ major_id: state.selectedMajor.id, selected_courses: courses }) });
  state.lastConflictChanges = data.recommended_changes || [];
  $("#conflictResult").innerHTML = evidenceNotice(data) + renderConflictResult(data, data.normalized_courses || courses);
  $("#applyConflictChanges")?.addEventListener("click", applyConflictChanges);
}

function renderConflictResult(data, courses) {
  const days = ["周一", "周二", "周三", "周四", "周五"];
  const dayMap = {"周一":1,"周二":2,"周三":3,"周四":4,"周五":5};
  const timeslots = ["08:00-09:40", "10:00-11:40", "14:30-16:10", "16:20-18:00", "19:00-20:40"];
  const conflictSet = new Set();
  for (const c of (data.conflicts || [])) {
    conflictSet.add(c.left.name);
    conflictSet.add(c.right.name);
  }
  let html = `<div class="timetable-container"><div class="timetable-header"><h3>📅 课表冲突检测</h3><span class="credits-badge">${courses.length} 门有效课程 · ${data.conflicts.length} 组冲突</span></div>`;
  html += `<div class="conflict-audit-summary ${data.conflicts?.length ? "has-conflict" : "is-clear"}">
    <strong>${escapeHtml(data.summary || "")}</strong>
    <span>原始 ${Number(data.input_count ?? courses.length)} 条</span>
    <span>去重后 ${Number(data.course_count ?? courses.length)} 条</span>
  </div>`;
  if (data.invalid_entries?.length || data.duplicate_entries?.length || data.duplicate_courses?.length) {
    html += `<div class="conflict-data-warnings">`;
    for (const item of data.invalid_entries || []) {
      html += `<div>⚠ ${escapeHtml(item.name)}：${(item.errors || []).map(escapeHtml).join("、")}</div>`;
    }
    if (data.duplicate_entries?.length) {
      html += `<div>🧹 已忽略 ${data.duplicate_entries.length} 条完全重复的课程记录。</div>`;
    }
    if (data.duplicate_courses?.length) {
      html += `<div>🔎 同名课程出现多个时段，请确认是否误选多个教学班：${data.duplicate_courses.map(escapeHtml).join("、")}</div>`;
    }
    html += `</div>`;
  }
  html += `<div class="conflict-week-grid">`;
  html += `<div class="timetable-day-header">时间</div>`;
  for (const d of days) html += `<div class="timetable-day-header">${d}</div>`;
  let idx = 0;
  for (const ts of timeslots) {
    html += `<div class="timeslot-label">${ts}</div>`;
    for (const d of days) {
      const daysMap = {1:"周一",2:"周二",3:"周三",4:"周四",5:"周五"};
      const matched = courses.filter(c => {
        const cd = c.dayNum || c.day || "";
        const cs = c.startTime || c.start || "";
        const dayStr = typeof cd === "number" ? daysMap[cd] || "" : cd;
        return dayStr === d && cs.startsWith(ts.substring(0,2));
      });
      html += `<div class="day-slot">`;
      for (const c of matched) {
        const isConflict = conflictSet.has(c.name);
        html += `<div class="conflict-card${isConflict ? " conflicting" : ""}">${escapeHtml(c.name)}<br><span style="color:#64748b;font-size:8px">${escapeHtml(c.category || "")}</span></div>`;
      }
      html += `</div>`;
    }
    idx++;
  }
  html += `</div></div>`;
  if (data.conflicts && data.conflicts.length > 0) {
    html += `<div style="padding:10px 14px"><h4 style="color:#ef4444;font-size:13px;margin:0 0 8px">冲突详情</h4>`;
    for (const c of data.conflicts) {
      html += `<div style="font-size:12px;color:#334155;padding:6px 0;border-bottom:1px solid rgba(148,163,184,0.18)">`;
      html += `<span style="color:#f87171">${escapeHtml(c.left.name)}</span> 与 <span style="color:#f87171">${escapeHtml(c.right.name)}</span>：${escapeHtml(c.reason)}`;
      html += `</div>`;
    }
    html += `</div>`;
  }
  if (data.alternatives && data.alternatives.length > 0) {
    html += `<div style="padding:0 14px 10px"><h4 style="color:#0ea5e9;font-size:13px;margin:8px 0">替代建议</h4>`;
    html += `<div style="display:flex;gap:4px;flex-wrap:wrap">`;
    for (const alt of data.alternatives.slice(0, 8)) {
      html += `<span style="padding:3px 10px;border-radius:6px;font-size:11px;background:rgba(14,165,233,0.08);border:1px solid rgba(14,165,233,0.12);color:#94a3b8">${escapeHtml(alt.name || alt)}</span>`;
    }
    html += `</div></div>`;
  }
  if (data.plans && data.plans.length > 0) {
    html += `<div style="padding:0 14px 10px"><h4 style="color:#0ea5e9;font-size:13px;margin:8px 0">调整方案</h4>`;
    for (const plan of data.plans) {
      html += `<div class="conflict-plan"><strong>${escapeHtml(plan.name)}</strong><span>${escapeHtml(plan.strategy)}</span>`;
      if (plan.changes?.length) {
        html += `<small>${plan.changes.map((change) => {
          if (change.action === "reschedule") {
            return `${escapeHtml(change.course)}：${escapeHtml(change.from?.day)} ${escapeHtml(change.from?.start)} → ${escapeHtml(change.to?.day)} ${escapeHtml(change.to?.start)}`;
          }
          if (change.action === "defer") {
            return `${escapeHtml(change.course)}：顺延至第${Number(change.to_semester)}学期`;
          }
          return `替代为 ${escapeHtml(change.name || change.course || "")}`;
        }).join("<br>")}</small>`;
      }
      html += `</div>`;
    }
    if (data.recommended_changes?.length) {
      html += `<button class="primary" id="applyConflictChanges">应用推荐错峰方案</button>`;
    }
    html += `</div>`;
  }
  return html;
}

async function applyConflictChanges() {
  const changes = state.lastConflictChanges || [];
  if (!changes.length) {
    showToast("当前没有可应用的自动调整。", "error");
    return;
  }
  const dayMap = {"周一":1,"周二":2,"周三":3,"周四":4,"周五":5};
  let applied = 0;
  for (const change of changes) {
    if (change.action !== "reschedule") continue;
    const course = (state.conflictCourses || []).find((item) => {
      const itemDay = ({1:"周一",2:"周二",3:"周三",4:"周四",5:"周五"})[item.dayNum] || item.day;
      return item.name === change.course
        && itemDay === change.from?.day
        && (item.startTime || item.start) === change.from?.start;
    });
    if (!course) continue;
    course.dayNum = dayMap[change.to?.day] || course.dayNum;
    course.startTime = change.to?.start || course.startTime;
    course.endTime = change.to?.end || course.endTime;
    applied += 1;
  }
  renderConflict();
  await runConflict();
  showToast(`已应用 ${applied} 项错峰调整，并重新检查冲突。`);
}

function removeConflictCourse(idx) {
  state.conflictCourses = state.conflictCourses || [];
  state.conflictCourses.splice(idx, 1);
  renderConflict();
}

function coursesFromAnalysis(courses) {
  const dayMap = {周一:1, 周二:2, 周三:3, 周四:4, 周五:5, 周六:6, 周日:7};
  return (courses || []).map((course) => ({
    name: course.name,
    dayNum: dayMap[course.day] || 1,
    startTime: course.start || "08:00",
    endTime: course.end || "09:40",
    category: course.category || "未分类",
    semester: course.semester || 1,
  }));
}

async function analyzeUploadedFile(file, prompt = "") {
  const form = new FormData();
  form.append("file", file);
  if (prompt) form.append("prompt", prompt);
  return api("/api/files/analyze", { method: "POST", body: form });
}

async function handleConflictFileUpload(e) {
  const file = e.target?.files?.[0];
  if (!file) return;
  const resultDiv = $("#conflictResult");
  if (resultDiv) {
    resultDiv.innerHTML = `<div style="padding:12px;text-align:center;color:#64748b;font-size:12px">正在分析 ${escapeHtml(file.name)}，请稍候...</div>`;
  }
  try {
    const result = await analyzeUploadedFile(file, "请提取课表中的全部课程，用于课程冲突检查。");
    if (!result.courses?.length) {
      throw new Error(result.summary || "未能识别出课程，请换一张更清晰的截图或检查文件内容");
    }
    state.conflictCourses = coursesFromAnalysis(result.courses);
    renderConflict();
    await runConflict();
    appendNotification(`已从 ${escapeHtml(file.name)} 导入 ${result.courses.length} 门课程`);
  } catch (err) {
    const target = $("#conflictResult");
    if (target) target.innerHTML = `<div style="padding:12px;text-align:center;color:#ef4444;font-size:12px">分析课表失败：${escapeHtml(err.message)}</div>`;
  } finally {
    if (e.target) e.target.value = "";
  }
}

// ═════════════════════════════════════════════════════════════════════
// 每用户独立的大模型 API 配置
// ═════════════════════════════════════════════════════════════════════

function initLlmSettings() {
  $("#llmSettingsButton").addEventListener("click", openLlmSettings);
  $("#llmSettingsClose").addEventListener("click", closeLlmSettings);
  $("#llmSettingsCancel").addEventListener("click", closeLlmSettings);
  $("#llmSettingsTest").addEventListener("click", testLlmConnection);
  $("#llmProvider").addEventListener("change", () => syncLlmProviderFields(true));
  $("#llmSettingsForm").addEventListener("submit", saveLlmSettings);
  $("#llmSettingsOverlay").addEventListener("click", (event) => {
    if (event.target.id === "llmSettingsOverlay") closeLlmSettings();
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !$("#llmSettingsOverlay").hidden) closeLlmSettings();
  });
}

function llmPreset(providerId) {
  return (state.llmConfig?.presets || []).find((item) => item.id === providerId);
}

async function openLlmSettings() {
  const overlay = $("#llmSettingsOverlay");
  const message = $("#llmSettingsMessage");
  overlay.hidden = false;
  message.textContent = "正在读取当前账号的配置…";
  message.className = "llm-settings-message";
  try {
    state.llmConfig = await api("/api/llm/config");
    $("#llmProvider").innerHTML = state.llmConfig.presets
      .map((item) => `<option value="${escapeHtml(item.id)}">${escapeHtml(item.label)}</option>`)
      .join("");
    $("#llmProvider").value = state.llmConfig.provider || "server";
    $("#llmBaseUrl").value = state.llmConfig.base_url || "";
    $("#llmModel").value = state.llmConfig.model || "";
    $("#llmApiKey").value = "";
    syncLlmProviderFields(false);
    message.textContent = state.llmConfig.status?.last_error
      ? "最近一次调用失败，可更换当前账号的 API 配置。"
      : "";
  } catch (error) {
    message.textContent = error.message;
    message.className = "llm-settings-message error";
  }
}

function closeLlmSettings() {
  $("#llmSettingsOverlay").hidden = true;
  $("#llmApiKey").value = "";
}

function syncLlmProviderFields(resetDefaults) {
  const provider = $("#llmProvider").value;
  const preset = llmPreset(provider);
  const isServer = provider === "server";
  const isCustom = provider === "custom";
  $("#llmPersonalFields").hidden = isServer;
  $("#llmBaseUrl").readOnly = !isCustom;
  $("#llmBaseUrl").required = !isServer;
  $("#llmModel").required = !isServer;
  if (resetDefaults && preset) {
    $("#llmBaseUrl").value = preset.base_url || "";
    $("#llmModel").value = preset.model || "";
    $("#llmApiKey").value = "";
  }
  $("#llmKeyState").textContent = isServer
    ? ""
    : state.llmConfig?.has_api_key
      ? "当前账号已有加密密钥；不填写新密钥会继续使用原密钥。"
      : "当前账号尚未保存 API Key。";
  $("#llmSettingsMessage").textContent = "";
  $("#llmSettingsMessage").className = "llm-settings-message";
}

async function saveLlmSettings(event) {
  event.preventDefault();
  const saveButton = $("#llmSettingsSave");
  const message = $("#llmSettingsMessage");
  saveButton.disabled = true;
  message.textContent = "正在保存…";
  message.className = "llm-settings-message";
  try {
    const result = await api("/api/llm/config", {
      method: "PUT",
      body: JSON.stringify({
        provider: $("#llmProvider").value,
        base_url: $("#llmBaseUrl").value.trim(),
        model: $("#llmModel").value.trim(),
        api_key: $("#llmApiKey").value.trim(),
      }),
    });
    state.llmConfig = result;
    state.meta.llm = result.status;
    state.llmEnabled = result.status.enabled;
    syncToggles();
    updateLlmStatus();
    message.textContent = result.source === "personal"
      ? "已保存当前账号的独立 API 配置。"
      : "已恢复平台默认配置。";
    message.className = "llm-settings-message success";
    setTimeout(closeLlmSettings, 700);
  } catch (error) {
    message.textContent = error.message;
    message.className = "llm-settings-message error";
  } finally {
    saveButton.disabled = false;
  }
}

async function testLlmConnection() {
  const button = $("#llmSettingsTest");
  const message = $("#llmSettingsMessage");
  button.disabled = true;
  message.textContent = "正在测试已保存的 API 配置…";
  message.className = "llm-settings-message";
  try {
    const result = await api("/api/llm/test", {
      method: "POST",
      body: "{}",
    });
    message.textContent = `连接成功：${result.provider} / ${result.model}，耗时 ${result.latency_ms} ms。`;
    message.className = "llm-settings-message success";
  } catch (error) {
    message.textContent = `连接失败：${error.message}。如刚修改了配置，请先保存后再测试。`;
    message.className = "llm-settings-message error";
  } finally {
    button.disabled = false;
  }
}

function appendNotification(msg) {
  const result = $("#conflictResult");
  if (result) {
    result.insertAdjacentHTML("afterbegin", '<div style="padding:8px;margin-bottom:8px;border-radius:6px;background:rgba(14,165,233,0.06);border:1px solid rgba(14,165,233,0.12);font-size:12px;color:#94a3b8">' + msg + "</div>");
  }
}
function addConflictCourse() {
  state.conflictCourses = state.conflictCourses || [];
  const pool = [...new Set((state.curriculum?.courses || []).map(c => c.name))];
  const name = pool.find(n => !state.conflictCourses.find(c => c.name === n)) || pool[0] || "新课程";
  const dayNum = Math.floor(Math.random() * 5) + 1;
  const startHour = 8 + Math.floor(Math.random() * 12);
  state.conflictCourses.push({
    name: name,
    dayNum: dayNum,
    startTime: `${String(startHour).padStart(2,"0")}:00`,
    endTime: `${String(startHour+1).padStart(2,"0")}:40`,
    category: "专业必修"
  });
  renderConflict();
}

// ── 教授匹配 ──────────────────────────────────────────────────────

async function renderProfessor() {
  if (!state.teacherRoster) state.teacherRoster = await api("/api/teacher-roster?limit=0");
  if (!state.facultyProfiles) state.facultyProfiles = await api("/api/faculty-profiles?limit=0");
  if (!state.teacherRosterFilters.college && !state.teacherRosterFilters.q && state.selectedMajor?.college && state.teacherRoster.colleges.includes(state.selectedMajor.college)) state.teacherRosterFilters.college = state.selectedMajor.college;
  if (!state.facultyFilters.college && !state.facultyFilters.q && state.selectedMajor?.college && state.facultyProfiles.colleges.includes(state.selectedMajor.college)) state.facultyFilters.college = state.selectedMajor.college;
  $("#tabBody").innerHTML = `
    <div class="grid-2">
      <section class="panel">
        <h2>教授研究方向匹配</h2>
        <div class="actions">
          <label><span>你的研究兴趣</span><textarea id="interestInput">我想做大模型、自然语言处理和智能软件工程</textarea></label>
          <button class="primary" id="matchBtn">计算相似度</button>
        </div>
      </section>
      <section class="panel">
        <h2>按课程查看任课老师</h2>
        <div class="actions">
          <label><span>课程名称</span><input id="teacherCourse" value="${escapeHtml(state.curriculum?.first_required_courses?.[0]?.name || "机器学习")}" /></label>
          <button class="primary" id="teacherBtn">查询老师</button>
        </div>
      </section>
    </div>
    <section class="panel">
      <h2>真实教师名单</h2>
      <div class="actions">
        <label><span>学院</span><select id="rosterCollege">${optionList(state.teacherRoster.colleges, "全部学院")}</select></label>
        <label><span>老师姓名 / 教师号</span><input id="rosterQuery" placeholder="例如 张三、T12345" value="${escapeHtml(state.teacherRosterFilters.q)}" /></label>
        <label><span>排课状态</span><select id="rosterScheduled"><option value="">全部</option><option value="是">已排课</option><option value="否">未排课</option></select></label>
        <button class="primary" id="rosterBtn">查询名单</button>
      </div>
      <div class="muted">名单来自导入的教师课表，字段包含教师号、姓名、所在单位、性别、是否已排课。</div>
    </section>
    <section class="panel" id="teacherRosterResult"><div class="empty-state">选择学院或输入老师姓名后查看真实教师名单。</div></section>
    <section class="panel">
      <h2>官方教师职称表</h2>
      <div class="actions">
        <label><span>学院 / 机构</span><select id="facultyCollege">${optionList(state.facultyProfiles.colleges, "全部机构")}</select></label>
        <label><span>职称</span><select id="facultyRank">${optionList(state.facultyProfiles.ranks, "全部职称")}</select></label>
        <label><span>姓名 / 方向 / 主页</span><input id="facultyQuery" placeholder="例如 李东旭、自然语言处理" value="${escapeHtml(state.facultyFilters.q)}" /></label>
        <label><span>导师身份</span><select id="facultyTutor"><option value="">全部</option><option value="graduate">研究生导师</option><option value="doctor">博士生导师</option></select></label>
        <button class="primary" id="facultyBtn">查询职称</button>
      </div>
      <div class="muted">数据来自华侨大学教师主页中文门户公开教师检索，包含职称、导师身份和教师主页链接。</div>
    </section>
    <section class="panel" id="facultyProfilesResult"><div class="empty-state">选择机构、职称或输入姓名后查看官方教师主页数据。</div></section>
    <section class="panel" id="professorResult"><div class="empty-state">输入兴趣或课程后查看结果。</div></section>
    <section class="panel">
      <h2>导入真实教务课表</h2>
      <p class="muted">把老师课表表格复制为 CSV/表格文本，粘贴到这里。字段支持：教师、课程、星期、开始、结束、校区、学院。</p>
      <div class="actions">
        <label><span>课表 CSV / 表格文本</span><textarea id="teacherScheduleImport" placeholder="教师,课程,星期,开始,结束,校区,学院&#10;张三,数据结构,周一,08:00,09:40,厦门校区,计算机科学与技术学院"></textarea></label>
        <button class="primary" id="importTeacherScheduleBtn">导入课表</button>
      </div>
      <div id="teacherScheduleImportResult" class="muted"></div>
    </section>`;
  $("#rosterCollege").value = state.teacherRosterFilters.college;
  $("#rosterScheduled").value = state.teacherRosterFilters.scheduled;
  $("#facultyCollege").value = state.facultyFilters.college;
  $("#facultyRank").value = state.facultyFilters.rank;
  $("#facultyTutor").value = state.facultyFilters.tutor;
  $("#matchBtn").addEventListener("click", runProfessorMatch);
  $("#teacherBtn").addEventListener("click", runTeacherLookup);
  $("#rosterBtn").addEventListener("click", loadTeacherRoster);
  $("#facultyBtn").addEventListener("click", loadFacultyProfiles);
  $("#rosterQuery").addEventListener("keydown", (e) => { if (e.key === "Enter") loadTeacherRoster(); });
  $("#facultyQuery").addEventListener("keydown", (e) => { if (e.key === "Enter") loadFacultyProfiles(); });
  $("#rosterCollege").addEventListener("change", loadTeacherRoster);
  $("#rosterScheduled").addEventListener("change", loadTeacherRoster);
  $("#facultyCollege").addEventListener("change", loadFacultyProfiles);
  $("#facultyRank").addEventListener("change", loadFacultyProfiles);
  $("#facultyTutor").addEventListener("change", loadFacultyProfiles);
  $("#importTeacherScheduleBtn").addEventListener("click", importTeacherSchedule);
  await loadTeacherRoster();
  await loadFacultyProfiles();
}

async function runProfessorMatch() {
  const interest = $("#interestInput").value.trim();
  const data = await api("/api/professors/match", {
    method: "POST", body: JSON.stringify({ interest_text: interest, top_k: 5 }),
  });
  $("#professorResult").innerHTML = `
    <h2>匹配结果</h2>
    <div class="result-list">
      ${data.map(p => `
        <div class="result-item">
          <div class="course-title">${escapeHtml(p.name)} · ${escapeHtml(p.title)} · 相似度 ${p.similarity}</div>
          <div class="course-meta">${escapeHtml(p.college)} · ${p.research_interests.map(escapeHtml).join("、")}</div>
          <div class="course-meta">近年论文：${p.papers.map(escapeHtml).join("；")}</div>
          ${p.homepage ? `<div class="course-meta"><a href="${escapeHtml(p.homepage)}" target="_blank" class="prof-link">📄 教师主页 →</a></div>` : ""}
        </div>`).join("")}
    </div>`;
}

async function runTeacherLookup() {
  const course = $("#teacherCourse").value.trim();
  const data = await api(`/api/professors?course=${encodeURIComponent(course)}`);
  $("#professorResult").innerHTML = `
    <h2>${escapeHtml(data.course)} 任课老师</h2>
    <div class="result-list">
      ${data.teachers.map(t => {
        const majors = t.majors?.length ? ` · 面向：${t.majors.slice(0,8).map(escapeHtml).join("、")}` : "";
        const credits = t.credits !== undefined ? ` · ${t.credits}学分` : "";
        return `<div class="result-item"><div class="course-title">${escapeHtml(t.name)}${credits}</div><div class="course-meta">${escapeHtml(t.college)} ${escapeHtml(t.title || "")}${majors}</div></div>`;
      }).join("")}
    </div>`;
}

async function importTeacherSchedule() {
  const text = $("#teacherScheduleImport").value.trim();
  if (!text) { $("#teacherScheduleImportResult").textContent = "请先粘贴老师课表数据。"; return; }
  const result = await api("/api/import/teacher-schedule", {
    method: "POST", body: JSON.stringify({ text }),
  });
  $("#teacherScheduleImportResult").textContent = `已导入 ${result.imported} 条，跳过重复 ${result.skipped} 条，当前真实课表记录 ${result.total} 条。重启后仍会保留。`;
}

async function loadTeacherRoster() {
  const collegeInput = $("#rosterCollege");
  const queryInput = $("#rosterQuery");
  const scheduledInput = $("#rosterScheduled");
  const college = collegeInput ? collegeInput.value : state.teacherRosterFilters.college || "";
  const q = queryInput ? queryInput.value.trim() : state.teacherRosterFilters.q || "";
  const scheduled = scheduledInput ? scheduledInput.value : state.teacherRosterFilters.scheduled || "";
  state.teacherRosterFilters = { college, q, scheduled };
  const params = new URLSearchParams({ limit: "300" });
  if (college) params.set("college", college);
  if (q) params.set("q", q);
  if (scheduled) params.set("scheduled", scheduled);
  const data = await api(`/api/teacher-roster?${params.toString()}`);
  state.teacherRoster = data;
  renderTeacherRoster(data);
}

function renderTeacherRoster(data) {
  const target = $("#teacherRosterResult");
  if (!target) return;
  const rows = data.teachers || [];
  if (rows.length === 0) { target.innerHTML = `<div class="empty-state">没有匹配的教师记录</div>`; return; }
  
  const filters = state.teacherRosterFilters;
  const title = filters.college || filters.q || filters.scheduled ? "筛选结果" : "教师名单";
  const limited = data.total > rows.length ? `，当前展示前 ${rows.length} 条` : "";
  
  const courseSummary = (teacher) => {
    const courses = teacher.courses_taught || [];
    if (!courses.length) return "-";
    return courses.slice(0, 5).map(c => {
      const majors = c.majors?.length ? `（${c.majors.slice(0, 3).join("、")}）` : "";
      return `${c.course} ${c.credits}学分${majors}`;
    }).join("、") + (courses.length > 5 ? `…等${courses.length}门` : "");
  };

  target.innerHTML = `
    <h2>${title}（共 ${data.total} 条${limited}）</h2>
    <div class="table-wrap"><table class="table">
      <thead><tr><th>教师号</th><th>姓名</th><th>学院</th><th>性别</th><th>已排课</th><th>授课课程</th></tr></thead>
      <tbody>${rows.map(r => `<tr>
        <td>${escapeHtml(r.teacher_id || "")}</td>
        <td>${escapeHtml(r.name || "")}</td>
        <td>${escapeHtml(r.college || "")}</td>
        <td>${escapeHtml(r.gender || "")}</td>
        <td>${escapeHtml(r.scheduled || "")}</td>
        <td style="font-size:12px;max-width:300px">${escapeHtml(courseSummary(r))}</td>
      </tr>`).join("")}</tbody>
    </table></div>`;
}

async function loadFacultyProfiles() {
  const collegeInput = $("#facultyCollege");
  const rankInput = $("#facultyRank");
  const queryInput = $("#facultyQuery");
  const tutorInput = $("#facultyTutor");
  const college = collegeInput ? collegeInput.value : state.facultyFilters.college || "";
  const rank = rankInput ? rankInput.value : state.facultyFilters.rank || "";
  const q = queryInput ? queryInput.value.trim() : state.facultyFilters.q || "";
  const tutor = tutorInput ? tutorInput.value : state.facultyFilters.tutor || "";
  state.facultyFilters = { college, rank, q, tutor };
  const params = new URLSearchParams({ limit: "200" });
  if (college) params.set("college", college);
  if (rank) params.set("rank", rank);
  if (q) params.set("q", q);
  if (tutor) params.set("tutor", tutor);
  const data = await api(`/api/faculty-profiles?${params.toString()}`);
  renderFacultyProfiles(data);
}

function renderFacultyProfiles(data) {
  const target = $("#facultyProfilesResult");
  if (!target) return;
  const rows = data.teachers || [];
  if (rows.length === 0) { target.innerHTML = `<div class="empty-state">没有匹配的官方教师主页记录</div>`; return; }
  target.innerHTML = `
    <h2>官方教师职称表（共 ${data.total} 条${data.total > rows.length ? `，显示前 ${rows.length} 条` : ""}）</h2>
    <div class="table-wrap"><table class="table">
      <thead><tr><th>姓名</th><th>职称</th><th>学院 / 机构</th><th>导师身份</th><th>主页</th></tr></thead>
      <tbody>${rows.map(t => {
        const colleges = t.colleges?.length ? t.colleges.join("、") : t.unit_raw || "-";
        const tutor = [t.doctor_tutor, t.graduate_tutor].filter(Boolean).join("、") || "-";
        const homepage = t.homepage ? `<a href="${escapeHtml(t.homepage)}" target="_blank">打开</a>` : "-";
        return `<tr><td>${escapeHtml(t.name)}</td><td>${escapeHtml(t.title || "-")}</td><td>${escapeHtml(colleges)}</td><td>${escapeHtml(tutor)}</td><td>${homepage}</td></tr>`;
      }).join("")}</tbody>
    </table></div>`;
}

// ── 普通聊天标签 ──────────────────────────────────────────────────

function renderChat() {
  $("#tabBody").innerHTML = `
    <section class="panel">
      <h2>与勤勉自由问答</h2>
      <div class="chat-toolbar"><label><span>对话人格</span><select id="chatPersona"></select></label>
        <div class="muted">${escapeHtml(currentPersona()?.description || "")}</div></div>
      <div class="chat-log" id="chatLog">${state.chat.map(chatBubble).join("")}</div>
      <div class="actions" style="margin-top:12px"><label><span>问题</span><input id="chatInput" placeholder="例如：算法工程师怎么排课？" /></label><button class="primary" id="chatBtn">发送</button></div>
    </section>`;
  syncPersonaControls();
  $("#chatBtn").addEventListener("click", sendChat);
  $("#chatInput").addEventListener("keydown", (e) => { if (e.key === "Enter") sendChat(); });
  $$("[data-suggest]").forEach((b) => { b.addEventListener("click", () => { $("#chatInput").value = b.dataset.suggest; sendChat(); }); });
  const log = $("#chatLog"); if (log) log.scrollTop = log.scrollHeight;
  const send = $("#chatBtn"); const input = $("#chatInput");
  if (send) send.disabled = state.chatBusy;
  if (input) input.disabled = state.chatBusy;
}

// ═════════════════════════════════════════════════════════════════════
// 浮动聊天
// ═════════════════════════════════════════════════════════════════════

function initFloatingChat() {
  const box = $("#floatingChat");
  const toggle = $("#floatingChatToggle");
  const send = $("#floatingChatSend");
  const input = $("#floatingChatInput");
  if (!box || !toggle || !send || !input) return;
  toggle.addEventListener("click", () => {
    state.floatingChatOpen = !state.floatingChatOpen;
    box.classList.toggle("open", state.floatingChatOpen);
    toggle.textContent = state.floatingChatOpen ? "−" : "+";
  });
  send.addEventListener("click", sendFloatingChat);
  input.addEventListener("keydown", (e) => { if (e.key === "Enter") sendFloatingChat(); });
}

function renderFloatingChat() {
  const box = $("#floatingChat");
  const log = $("#floatingChatLog");
  if (!box || !log) return;
  box.classList.toggle("open", state.floatingChatOpen);
  $("#floatingChatToggle").textContent = state.floatingChatOpen ? "−" : "+";
  log.innerHTML = state.chat.map(chatBubble).join("");
  const send = $("#floatingChatSend");
  const input = $("#floatingChatInput");
  if (send) send.disabled = state.chatBusy;
  if (input) input.disabled = state.chatBusy;
  log.querySelectorAll("[data-suggest]").forEach((b) => {
    b.addEventListener("click", () => { $("#floatingChatInput").value = b.dataset.suggest; sendFloatingChat(); });
  });
  log.scrollTop = log.scrollHeight;
}

async function sendFloatingChat() {
  const input = $("#floatingChatInput");
  const message = input.value.trim();
  if (!message || state.chatBusy) return;
  
  // 确保有持久化对话 ID（与 AI 全屏共享同一对话）
  if (!state.activeConvId) {
    try {
      const conv = await api("/api/conversations", { method: "POST", body: JSON.stringify({ title: "悬浮框对话" }) });
      state.activeConvId = conv.id;
      state.floatingConvId = conv.id;
    } catch (_) {}
  }
  
  state.chat.push({ role: "user", text: message });
  const thinkingId = addThinkingMessage();
  state.chatBusy = true;
  input.value = "";
  renderFloatingChat();
  try {
    const response = await api("/api/chat", {
      method: "POST",
      body: JSON.stringify({
        message,
        conversation_id: state.activeConvId,
        context: chatContext(),
      }),
    });
    rememberResponseContext(response);
    replaceChatMessage(thinkingId, {
      role: "assistant",
      text: response.answer,
      suggestions: response.suggestions || [],
      answerMode: response.answer_mode,
      grounding: response.grounding,
    });
    // AI→Professor sync: 根据意图切换标签页
    if (state.activeTab === "professor" && !state.aiPageOpen) {
      await renderTab();
    }
    // AI全屏页面也同步该消息
    if (state.aiPageOpen) {
      state.aiConversation.push({ role: "user", content: `[悬浮框] ${message}` });
      state.aiConversation.push({
        role: "assistant",
        content: response.answer,
        extraHtml: renderAnswerModeBadge(response),
      });
      renderAiMessages();
    }
  } catch (error) {
    replaceChatMessage(thinkingId, { role: "assistant", text: `请求失败：${error.message}`, suggestions: ["再试一次", "检查大模型 API 配置"] });
  } finally {
    state.chatBusy = false;
    renderFloatingChat();
  }
}

function chatContext() {
  const teacherName = state.lastTeacherName || state.teacherRosterFilters.q || state.facultyFilters.q;
  const historyItems = state.chat.filter((item) => !item.thinking);
  if (historyItems.at(-1)?.role === "user") historyItems.pop();
  const recentHistory = historyItems.slice(-12).map((item) => ({ role: item.role, text: item.text }));
  return {
    persona: state.persona,
    major_id: state.selectedMajor?.id,
    student_type: state.studentType,
    teacher_college: state.teacherRosterFilters.college,
    teacher_q: teacherName,
    last_teacher_name: state.lastTeacherName,
    teacher_scheduled: state.teacherRosterFilters.scheduled,
    chat_history: recentHistory,
    knowledge_base_enabled: state.memoryEnabled,
  };
}

function chatBubble(item) {
  const displayText = item.role === "assistant" && !item.thinking
    ? renderMarkdownSafe(item.text || "")
    : escapeHtml(item.text || "").replace(/\n/g, "<br>");
  return `<div class="chat-message ${item.role} ${item.thinking ? "thinking" : ""}">
    <div>${item.thinking ? thinkingHtml(item.text) : displayText}</div>
    ${item.role === "assistant" && !item.thinking ? renderAnswerModeBadge(item) : ""}
    ${item.suggestions?.length ? `<div class="suggestions">${item.suggestions.map((text) => `<button data-suggest="${escapeHtml(text)}">${escapeHtml(text)}</button>`).join("")}</div>` : ""}
  </div>`;
}

function thinkingText() {
  return `${currentPersona()?.name || "勤勉"}思考中`;
}

function thinkingHtml(text) {
  return `<span class="thinking-label">${escapeHtml(text)}</span><span class="thinking-dots"><i></i><i></i><i></i></span>`;
}

function addThinkingMessage() {
  const id = `thinking-${Date.now()}-${Math.random().toString(16).slice(2)}`;
  state.chat.push({ id, role: "assistant", text: thinkingText(), thinking: true, suggestions: [] });
  return id;
}

function replaceChatMessage(id, next) {
  const index = state.chat.findIndex((item) => item.id === id);
  if (index >= 0) state.chat[index] = next;
  else state.chat.push(next);
}

async function sendChat() {
  const input = $("#chatInput");
  const message = input.value.trim();
  if (!message || state.chatBusy) return;
  state.chat.push({ role: "user", text: message });
  const thinkingId = addThinkingMessage();
  state.chatBusy = true;
  input.value = "";
  renderChat();
  renderFloatingChat();
  try {
    const response = await api("/api/chat", { method: "POST", body: JSON.stringify({ message, context: chatContext() }) });
    rememberResponseContext(response);
    replaceChatMessage(thinkingId, {
      role: "assistant",
      text: response.answer,
      suggestions: response.suggestions || [],
      answerMode: response.answer_mode,
      grounding: response.grounding,
    });
  } catch (error) {
    replaceChatMessage(thinkingId, { role: "assistant", text: `请求失败：${error.message}`, suggestions: ["再试一次", "检查大模型 API 配置"] });
  } finally {
    state.chatBusy = false;
    renderFloatingChat();
    renderChat();
  }
}

function rememberResponseContext(response) {
  const data = response?.data || {};
  const intent = response?.intent;
  if (data.teacher_name) {
    const hasMatch = (data.total ?? 0) > 0 || (data.course_total ?? 0) > 0 || (data.teachers?.length ?? 0) > 0 || (data.courses?.length ?? 0) > 0;
    if (hasMatch) {
      state.lastTeacherName = data.teacher_name;
      localStorage.setItem(userStorageKey("last_teacher"), data.teacher_name);
    }
  }
  // AI→Professor sync: auto-switch tab and set filters (仅指名查询时跳转)
  if (intent === "college_teacher_roster" || intent === "major_college_teacher_roster") {
    state.teacherRosterFilters = { college: data.college || "", q: "", scheduled: "" };
    // 仅更新筛选条件，不自动跳转标签页
  }
  if (intent === "teacher_roster_lookup") {
    state.teacherRosterFilters = { college: "", q: data.teacher_name || "", scheduled: "" };
    state.activeTab = "professor";
  }
  if (intent === "faculty_profiles") {
    state.facultyFilters = { college: data.college || "", rank: data.rank || "", tutor: data.tutor || "", q: "" };
    state.activeTab = "professor";
  }
  if (intent === "faculty_profile_lookup") {
    state.facultyFilters = { college: "", rank: "", tutor: "", q: data.teacher_name || "" };
    state.activeTab = "professor";
  }
  // AI to Career sync
  if (intent === "career_plan" && data.matched_role) {
    state.activeTab = "career";
    setTimeout(() => {
      const input = document.getElementById("careerInput");
      if (input) { input.value = data.matched_role; generateCareerPlan(); }
    }, 200);
  }
  // AI to Conflict sync
  if (intent === "conflict" && data.conflicts?.length > 0) {
    state.activeTab = "conflict";
  }
  // AI to Curriculum sync
  if (intent === "curriculum" && data.major?.id) {
    state.activeTab = "majors";
  }
  // AI to CreditCheck sync
  if (intent === "credit_check" && data.total_gap !== undefined) {
    state.activeTab = "credits";
  }
}

// ═════════════════════════════════════════════════════════════════════
// 人格系统
// ═════════════════════════════════════════════════════════════════════

function personaOptions() {
  const personas = state.meta?.personas || [];
  return personas.map((p) => `<option value="${escapeHtml(p.id)}">${escapeHtml(p.name)}</option>`).join("");
}

function currentPersona() {
  return (state.meta?.personas || []).find((p) => p.id === state.persona);
}

function syncPersonaControls() {
  ["floatingPersona", "chatPersona", "aiPersona"].forEach((id) => {
    const select = document.getElementById(id);
    if (!select) return;
    select.innerHTML = personaOptions();
    select.value = state.persona;
    select.onchange = () => setPersona(select.value, true);
  });
  updateLlmStatus();
}

function setPersona(personaId, announce = false) {
  const exists = (state.meta?.personas || []).some((p) => p.id === personaId);
  state.persona = exists ? personaId : "diligent";
  localStorage.setItem(userStorageKey("persona"), state.persona);
  syncPersonaControls();
  // 应用主题色
  applyPersonaTheme(state.persona);
  if (announce) {
    const persona = currentPersona();
    const color = persona?.color || "#0ea5e9";
    const icon = persona?.icon || "☀";
    state.chat.push({ role: "assistant", text: `${icon} 已切换为「${persona?.name || "勤勉原版"}」（${persona?.color_name || ""}）。之后我会按这个风格和你对话。`, suggestions: ["你好", "你能做什么", "计算机学院教授有哪些"] });
    renderFloatingChat();
  }
}

function applyPersonaTheme(personaId) {
  const persona = (state.meta?.personas || []).find((p) => p.id === personaId);
	  if (!persona || !persona.color) return;
	  const color = persona.color;
	  const root = document.documentElement;
	  root.style.setProperty("--persona-color", color);
	  root.style.setProperty("--persona-color-dim", color + "66");
	  // 背景主题渐变（白色为主 + 专属颜色晕染）
	  root.style.setProperty("--bg-theme-start", "#ffffff");
	  root.style.setProperty("--bg-theme-end", color + "15");
	  root.style.setProperty("--bg-theme-radial", color + "0a");
	  root.style.setProperty("--bg-theme-glow", color + "08");
	  // Also update the brand text
	  const brand = document.querySelector(".brand");
	  if (brand) brand.style.color = color;
	  // Update meta theme-color
	  const meta = document.querySelector('meta[name="theme-color"]');
	  if (meta) meta.content = color;
	}

// ═════════════════════════════════════════════════════════════════════
// AI 全屏助手页面
// ═════════════════════════════════════════════════════════════════════

async function openAiPage() {
  const overlay = $("#aiFullscreenPage");
  if (!overlay) return;
  overlay.classList.add("open");
  state.aiPageOpen = true;
  // 隐藏主应用
  $("#mainApp").style.display = "none";
  // 隐藏浮动聊天
  $("#floatingChat").style.display = "none";
  // 隐藏顶部栏
  document.querySelector(".topbar").style.display = "none";

  // 加载对话列表
  await loadConversations();

  // 激活粒子增强
  if (state.particleSystem) {
    state.particleSystem.addBurst(window.innerWidth / 2, window.innerHeight / 2, 30);
  }
}

function closeAiPage() {
  const overlay = $("#aiFullscreenPage");
  if (!overlay) return;
  overlay.classList.remove("open");
  state.aiPageOpen = false;
  $("#mainApp").style.display = "";
  $("#floatingChat").style.display = "";
  document.querySelector(".topbar").style.display = "";
}

function initAiPage() {
  // 关闭按钮
  $("#aiClosePage").addEventListener("click", closeAiPage);

  // 新建对话
  $("#aiNewConversation").addEventListener("click", () => newAiConversation());

  // 搜索对话
  $("#aiConvSearch").addEventListener("input", filterConversations);

  // 发送消息
  $("#aiChatSend").addEventListener("click", sendAiMessage);
  $("#aiChatInput").addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendAiMessage(); }
  });
  // 文件上传
  const uploadBtn = $("#aiUploadBtn");
  const fileInput = $("#aiFileInput");
  if (uploadBtn && fileInput) {
    uploadBtn.addEventListener("click", () => fileInput.click());
    fileInput.addEventListener("change", (e) => {
      if (e.target.files.length > 0) { handleFileUpload(e.target.files[0]); e.target.value = ""; }
    });
  }
  const removeBtn = $("#aiFileRemove");
  if (removeBtn) {
    removeBtn.addEventListener("click", clearFileUpload);
  }

  // 删除对话
  $("#aiDeleteConversation").addEventListener("click", deleteAiConversation);
  $("#aiExportConversation").addEventListener("click", exportAiConversation);

  // 清空记忆
  $("#aiClearMemory").addEventListener("click", clearKnowledgeBase);

  // AI全屏人格切换（委托到 syncPersonaControls）
  const aiPersona = $("#aiPersona");
  if (aiPersona) {
    aiPersona.addEventListener("change", () => setPersona(aiPersona.value, true));
  }

  // 欢迎页面的快捷入口
  $("#aiMessages").addEventListener("click", (e) => {
    const chip = e.target.closest("[data-suggest]");
    if (chip) {
      $("#aiChatInput").value = chip.dataset.suggest;
      sendAiMessage();
    }
  });

  // AI 消息中的建议按钮
  $("#aiMessages").addEventListener("click", (e) => {
    const btn = e.target.closest(".ai-msg-suggestions button");
    if (btn && btn.dataset.suggest) {
      $("#aiChatInput").value = btn.dataset.suggest;
      sendAiMessage();
    }
  });
}

// ── 对话管理 ──────────────────────────────────────────────────

async function loadConversations() {
  try {
    const data = await api("/api/conversations");
    state.conversations = data.conversations || [];
    renderConversationList();

    // 自动选择第一条或创建新的
    if (state.conversations.length > 0 && !state.activeConvId) {
      await selectConversation(state.conversations[0].id);
    } else if (state.conversations.length === 0) {
      await newAiConversation();
    } else if (state.activeConvId) {
      // 刷新当前选中的对话
      renderConversationList();
    }
  } catch (err) {
    console.error("Failed to load conversations:", err);
  }
}

function renderConversationList() {
  const list = $("#aiConvList");
  const count = $("#aiConvCount");
  if (!list) return;
  if (state.conversations.length === 0) {
    list.innerHTML = '<div class="ai-conv-empty">暂无对话，点击 ✚ 新建</div>';
    if (count) count.textContent = "0 条对话";
    return;
  }
  list.innerHTML = state.conversations
    .map(
      (conv) => {
        const isActive = state.activeConvId === conv.id;
        return `
        <div class="ai-conv-item ${isActive ? "active" : ""}" data-conv-id="${escapeHtml(conv.id)}">
          <div class="ai-conv-item-title" ${isActive ? 'ondblclick="startRenameConv(\'' + escapeHtml(conv.id) + '\', this)"' : ""}>${escapeHtml(conv.title || "未命名对话")}</div>
          <div class="ai-conv-item-meta">${escapeHtml(conv.created_at)} · ${conv.message_count} 条消息</div>
          ${state.activeConvId === conv.id ? '<button class="ai-conv-rename-btn" onclick="startRenameConv(\'' + escapeHtml(conv.id) + '\', this.parentElement.querySelector(\'.ai-conv-item-title\'))">✎</button>' : ""}
        </div>`;
      }
    )
    .join("");

  $$(".ai-conv-item").forEach((item) => {
    item.addEventListener("click", () => selectConversation(item.dataset.convId));
  });
  if (count) count.textContent = `${state.conversations.length} 条对话`;
}

function filterConversations() {
  const query = $("#aiConvSearch").value.trim().toLowerCase();
  const items = $$(".ai-conv-item");
  items.forEach((item) => {
    const title = item.querySelector(".ai-conv-item-title")?.textContent?.toLowerCase() || "";
    item.style.display = query && !title.includes(query) ? "none" : "";
  });
}

async function selectConversation(convId) {
  if (!convId) return;
  state.activeConvId = convId;
  renderConversationList();

  try {
    const conv = await api(`/api/conversations/${convId}`);
    state.aiConversation = conv.messages || [];

    // 更新标题
    const titleEl = $("#aiConvTitle");
    if (titleEl) titleEl.textContent = conv.title || "当前对话";
    const badge = $("#aiConvBadge");
    if (badge) badge.textContent = conv.message_count ? `${conv.message_count} 条` : "空";

    renderAiMessages();
  } catch (err) {
    console.error("Failed to load conversation:", err);
    state.aiConversation = [];
    renderAiMessages();
  }
}

async function newAiConversation() {
  try {
    const conv = await api("/api/conversations", { method: "POST", body: JSON.stringify({ title: "新对话" }) });
    state.activeConvId = conv.id;
    state.aiConversation = [];
    // 重新加载列表
    const data = await api("/api/conversations");
    state.conversations = data.conversations || [];
    renderConversationList();
    renderAiMessages();
    $("#aiConvTitle").textContent = "新对话";
    $("#aiConvBadge").textContent = "0 条";
    $("#aiChatInput").focus();
  } catch (err) {
    console.error("Failed to create conversation:", err);
  }
}

async function deleteAiConversation() {
  if (!state.activeConvId) return;
  if (!confirm("确定删除当前对话？此操作不可撤销。")) return;

  try {
    await api(`/api/conversations/${state.activeConvId}`, { method: "DELETE" });
    state.activeConvId = null;
    state.aiConversation = [];
    renderAiMessages();
    $("#aiConvTitle").textContent = "对话已删除";
    $("#aiConvBadge").textContent = "";
    await loadConversations();
  } catch (err) {
    console.error("Failed to delete conversation:", err);
  }
}

async function clearKnowledgeBase() {
  if (!confirm("确定清空知识库（长期记忆）？所有存储的对话摘要将被删除。")) return;
  try {
    await api("/api/knowledge/clear", { method: "POST" });
    alert("知识库已清空。");
  } catch (err) {
    console.error("Failed to clear knowledge base:", err);
  }
}

// ── 对话重命名 ──────────────────────────────────────────────

async function renameConversation(convId, newTitle) {
  try {
    const result = await api(`/api/conversations/${convId}/rename`, {
      method: "POST", body: JSON.stringify({ title: newTitle }),
    });
    // Update local conversations cache
    const idx = state.conversations.findIndex(c => c.id === convId);
    if (idx >= 0) state.conversations[idx].title = newTitle;
    renderConversationList();
    const titleEl = $("#aiConvTitle");
    if (titleEl && state.activeConvId === convId) titleEl.textContent = newTitle;
    return result;
  } catch (err) {
    console.error("Failed to rename conversation:", err);
    return null;
  }
}

function startRenameConv(convId, titleEl) {
  if (!titleEl) return;
  const currentTitle = titleEl.textContent || "";
  const input = document.createElement("input");
  input.type = "text";
  input.value = currentTitle;
  input.className = "ai-rename-input";
  input.style.width = "100%";
  input.style.boxSizing = "border-box";
  titleEl.textContent = "";
  titleEl.appendChild(input);
  input.focus();
  input.select();
  
  const finish = async () => {
    const newTitle = input.value.trim();
    if (newTitle && newTitle !== currentTitle) {
      await renameConversation(convId, newTitle);
    } else {
      titleEl.textContent = currentTitle;
    }
  };
  
  input.addEventListener("blur", finish);
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter") { e.preventDefault(); input.blur(); }
    if (e.key === "Escape") { titleEl.textContent = currentTitle; }
  });
}

// ── AI 消息渲染 ──────────────────────────────────────────────

function renderAiMessages() {
  const container = $("#aiMessages");
  if (!container) return;

  const messages = state.aiConversation;

  if (!messages || messages.length === 0) {
    // 显示欢迎页
    container.innerHTML = `
      <div class="ai-welcome">
        <div class="ai-welcome-icon">⚛</div>
        <h1>勤勉 AI 助手</h1>
        <p>华侨大学学业规划 · 辐射级智能分析 · 长期记忆已${state.memoryEnabled ? "开启" : "关闭"}</p>
        <div class="ai-welcome-suggestions">
          <button class="ai-chip" data-suggest="这个专业适合哪些职业">🧭 当前专业职业推荐</button>
          <button class="ai-chip" data-suggest="算法工程师完整学习路线怎么做">🎯 算法工程师课表</button>
          <button class="ai-chip" data-suggest="数据结构这门课难吗">⚡ 课程难度分析</button>
          <button class="ai-chip" data-suggest="计算机科学与技术学院有哪些老师">👨‍🏫 查老师</button>
          <button class="ai-chip" data-suggest="推荐热门5个专业方向">🔥 热门方向</button>
          <button class="ai-chip" data-suggest="人工智能专业毕业要多少学分">📊 学分查询</button>
          <button class="ai-chip" data-suggest="帮我做学分体检">💊 学分体检</button>
        </div>
      </div>`;
    return;
  }

  container.innerHTML = messages
    .map((msg, idx) => {
      const role = msg.role === "user" ? "user" : "assistant";
      const content = role === "assistant"
        ? renderMarkdownSafe(msg.content || "")
        : escapeHtml(msg.content || "").replace(/\n/g, "<br>");
      const avatar = role === "user" ? "👤" : "⚛";
      return `<div class="ai-msg ${role}">
        <div class="ai-msg-avatar">${avatar}</div>
        <div class="ai-msg-stack">
          <div class="ai-msg-bubble">${content}</div>
          ${msg.extraHtml ? `<div class="ai-msg-extra">${msg.extraHtml}</div>` : ""}
        </div>
      </div>`;
    })
    .join("");

  // 添加思考中指示器
  if (state.aiChatBusy) {
    container.innerHTML += `<div class="ai-msg assistant thinking">
      <div class="ai-msg-avatar">⚛</div>
      <div class="ai-msg-bubble">${thinkingHtml("勤勉思考中")}</div>
    </div>`;
  }

  container.scrollTop = container.scrollHeight;
}

function appendAiMessage(role, content, suggestions = [], extraHtml = "") {
  const container = $("#aiMessages");

  // 移除欢迎页（如果是第一条消息）
  const welcome = container.querySelector(".ai-welcome");
  if (welcome) {
    container.innerHTML = "";
  }

  // 移除思考中指示器
  const thinking = container.querySelector(".ai-msg.thinking");
  if (thinking) thinking.remove();

  const msgIndex = state.aiConversation.length;
  const avatar = role === "user" ? "👤" : "⚛";
  const displayContent = role === "assistant"
    ? renderMarkdownSafe(content || "")
    : escapeHtml(content || "").replace(/\n/g, "<br>");
  const html = `<div class="ai-msg ${role}" data-msg-index="${msgIndex}">
    <div class="ai-msg-avatar">${avatar}</div>
    <div class="ai-msg-stack">
      <div class="ai-msg-bubble">${displayContent}
        <button class="ai-msg-del" onclick="deleteAiMessage(${msgIndex})" title="删除此条消息">✕</button>
      </div>
      ${extraHtml ? `<div class="ai-msg-extra">${extraHtml}</div>` : ""}
    </div>
  </div>`;

  container.insertAdjacentHTML("beforeend", html);

  // 添加建议按钮（仅助手消息）
  if (role === "assistant" && suggestions.length > 0) {
    const suggHtml = `<div class="ai-msg-suggestions">${suggestions.map((s) => `<button data-suggest="${escapeHtml(s)}">${escapeHtml(s)}</button>`).join("")}</div>`;
    container.insertAdjacentHTML("beforeend", suggHtml);
  }

  container.scrollTop = container.scrollHeight;
}

async function deleteAiMessage(msgIndex) {
  if (!state.activeConvId) return;
  if (!confirm("确定删除此条消息？")) return;
  try {
    await api(`/api/conversations/${state.activeConvId}/messages/${msgIndex}`, { method: "DELETE" });
    state.aiConversation.splice(msgIndex, 1);
    renderAiMessages();
    // 刷新对话列表
    refreshConversationList();
  } catch (err) {
    console.error("Failed to delete message:", err);
  }
}

/**
 * 渲染课表规划的时间线卡片（当 intent 为 career_plan 时）
 */
function renderAiCareerRecommendations(data) {
  const rows = data?.recommendations || [];
  if (!rows.length) return "";
  return `
    <div class="ai-career-recommendations">
      <div class="ai-career-recommendations-title">
        ${escapeHtml(data.major?.display_name || "当前专业")} · 职业画像推荐
      </div>
      ${rows.map((role, index) => `
        <button type="button" class="ai-career-recommendation"
                data-suggest="${escapeHtml(data.major?.name || "")}专业的${escapeHtml(role.name)}职业画像与学习路线">
          <span class="ai-career-rank">${index + 1}</span>
          <span>
            <strong>${escapeHtml(role.name)}</strong>
            <small>${escapeHtml(role.category)} · ${role.score}% ${escapeHtml(role.level)}</small>
            <em>${escapeHtml(role.reason)}</em>
          </span>
        </button>
      `).join("")}
      <p>${escapeHtml(data.notice || "")}</p>
    </div>`;
}

function renderCareerPlanExtra(response) {
  const data = response.data || {};
  if (response.intent === "career_recommendations") {
    return renderAiCareerRecommendations(data);
  }
  const periods = data.planning_periods?.length ? data.planning_periods : data.semesters;
  if (!periods || !Array.isArray(periods) || periods.length === 0) return "";

  const matchedRole = escapeHtml(data.matched_role || "目标岗位");
  const majorName = escapeHtml(data.selected_major?.display_name || "");

  let html = `<div style="margin-top:8px">`;
  html += `<div style="display:flex;gap:10px;flex-wrap:wrap;margin-bottom:8px">`;
  html += `<span style="font-size:12px;color:#94a3b8">🎯 <strong style="color:#e2e8f0">${matchedRole}</strong></span>`;
  html += `<span style="font-size:12px;color:#94a3b8">🏛 <strong style="color:#e2e8f0">${majorName}</strong></span>`;
  html += `<span style="font-size:12px;color:#94a3b8">📚 ${data.program_years || ""} 学年 · ${periods.length} 个规划阶段</span>`;
  if (data.salary_range) html += `<span style="font-size:12px;color:#94a3b8">💰 <strong style="color:#22c55e">${data.salary_range}</strong></span>`;
  html += `</div>`;

  for (const sem of periods) {
    const credits = sem.credits || 0;
    const courses = sem.courses || [];
    html += `<div style="background:rgba(14,165,233,0.04);border:1px solid rgba(14,165,233,0.1);border-radius:8px;margin-bottom:6px;overflow:hidden;">`;
    html += `<div style="display:flex;justify-content:space-between;align-items:center;padding:8px 10px;background:rgba(14,165,233,0.06);font-size:12px;">`;
    html += `<span style="font-weight:600;color:#0ea5e9">${escapeHtml(sem.label)}</span>`;
    html += `<span style="color:#64748b;font-size:11px">${credits} 学分 · ${escapeHtml(sem.focus || "")}</span>`;
    html += `</div>`;
    html += `<div style="padding:6px 10px;display:flex;gap:4px;flex-wrap:wrap">`;
    for (const c of courses) {
      let bg = "rgba(14,165,233,0.08)";
      let border = "rgba(14,165,233,0.15)";
      let color = "#0ea5e9";
      const cat = c.category || "";
      if (cat.includes("选修")) { bg = "rgba(176,38,255,0.08)"; border = "rgba(176,38,255,0.15)"; color = "#c084fc"; }
      else if (cat.includes("通识")) { bg = "rgba(34,197,94,0.08)"; border = "rgba(34,197,94,0.15)"; color = "#4ade80"; }
      else if (cat.includes("实践")) { bg = "rgba(245,158,11,0.08)"; border = "rgba(245,158,11,0.15)"; color = "#fbbf24"; }
      html += `<span style="display:inline-block;padding:2px 8px;border-radius:6px;font-size:10px;background:${bg};color:${color};border:1px solid ${border}">${escapeHtml(c.name)}<span style="opacity:0.6;margin-left:3px">${c.credits}学分</span></span>`;
    }
    html += `</div></div>`;
  }

  if (data.must_courses && data.must_courses.length > 0) {
    html += `<div style="display:flex;gap:3px;flex-wrap:wrap;margin-top:4px;padding:0 4px">`;
    for (const c of data.must_courses.slice(0, 10)) {
      html += `<span style="font-size:9px;padding:1px 6px;border-radius:8px;background:rgba(14,165,233,0.06);color:#64748b;border:1px solid rgba(14,165,233,0.1)">${escapeHtml(c)}</span>`;
    }
    html += `</div>`;
  }

  if (data.milestones && data.milestones.length > 0) {
    html += `<div style="margin-top:6px;padding:0 4px">`;
    for (const m of data.milestones) {
      html += `<div style="font-size:10px;color:#64748b;padding:1px 0">· ${escapeHtml(m)}</div>`;
    }
    html += `</div>`;
  }

  html += `</div>`;
  return html;
}

function showAiThinking() {
  const container = $("#aiMessages");
  const thinking = container.querySelector(".ai-msg.thinking");
  if (thinking) return;
  container.insertAdjacentHTML("beforeend", `<div class="ai-msg assistant thinking">
    <div class="ai-msg-avatar">⚛</div>
    <div class="ai-msg-bubble">${thinkingHtml("勤勉思考中")}</div>
  </div>`);
  container.scrollTop = container.scrollHeight;
}

function hideAiThinking() {
  const thinking = document.querySelector("#aiMessages .ai-msg.thinking");
  if (thinking) thinking.remove();
}

// ── AI 对话发送 ──────────────────────────────────────────────


// ── 文件上传与分析 ──────────────────────────────────────────

async function handleFileUpload(file) {
  if (!file) return;
  state.aiChatBusy = true;
  showAiThinking();
  
  const filePreview = $("#aiFilePreview");
  const fileName = $("#aiFileName");
  if (filePreview && fileName) {
    filePreview.style.display = "block";
    fileName.textContent = "📄 " + file.name;
  }
  
  const msg = `[已上传文件：${file.name}] 正在分析...`;
  $("#aiChatInput").value = "";
  state.aiConversation.push({ role: "user", content: msg });
  appendAiMessage("user", msg);

  try {
    const result = await analyzeUploadedFile(file);
    hideAiThinking();
    if (result.courses && result.courses.length > 0) {
          // It's a timetable - store for conflict detection
          state.pendingVisionCourses = result.courses;
          const courseList = result.courses.map(c => c.name).join("、");
          let answer = result.summary || `已从图片中识别出 ${result.courses.length} 门课程：${courseList}`;
          
          if (result.intent === "conflict") {
            answer += "\n\n🔄 检测到可能是课表冲突问题，已自动切换到「冲突微调」页面并导入课程数据。";
            state.visionPendingAction = "conflict";
          } else if (result.intent === "career_plan") {
            answer += "\n\n🎯 检测到可能是职业规划问题，已自动切换到「职业规划」页面。";
            if (result.career) state.visionPendingCareer = result.career;
            state.visionPendingAction = "career";
          } else if (result.intent === "curriculum") {
            answer += "\n\n📚 检测到可能是培养方案查询，已自动切换到「专业目录」页面。";
            state.visionPendingAction = "curriculum";
          } else if (result.intent === "credit_check") {
            answer += "\n\n📊 检测到可能是学分检查，已自动切换到「学分体检」页面。";
            state.visionPendingAction = "credits";
          }
          
          state.aiConversation.push({ role: "assistant", content: answer });
          appendAiMessage("assistant", answer, ["检查课表冲突", "查看专业目录", "职业规划"]);
          state.chat.push({ role: "assistant", text: "[AI助手] " + answer.slice(0, 200) });
          renderFloatingChat();
          
          // Auto-navigate based on intent
          setTimeout(() => {
            if (result.intent === "conflict" && state.pendingVisionCourses?.length > 0) {
              state.conflictCourses = coursesFromAnalysis(state.pendingVisionCourses);
              state.activeTab = "conflict";
              renderTab();
            } else if (result.intent === "career_plan") {
              state.activeTab = "career";
              if (state.visionPendingCareer) {
                setTimeout(() => {
                  const input = $("#careerInput");
                  if (input) input.value = state.visionPendingCareer;
                  generateCareerPlan();
                }, 100);
              }
              renderTab();
            } else if (result.intent === "curriculum") {
              state.activeTab = "majors";
              renderTab();
            } else if (result.intent === "credit_check") {
              state.activeTab = "credits";
              renderTab();
            }
          }, 500);
    } else {
          // Not a timetable - treat as general chat
          const answer = result.summary || "已收到文件，但未能识别出课表信息。请检查文件内容或上传更清晰的截图。";
          state.aiConversation.push({ role: "assistant", content: answer });
          appendAiMessage("assistant", answer, ["上传课表截图", "算法工程师完整学习路线", "学分体检"]);
          state.chat.push({ role: "assistant", text: "[AI助手] " + answer.slice(0, 200) });
          renderFloatingChat();
    }
  } catch (err) {
    hideAiThinking();
    appendAiMessage("assistant", "文件分析失败：" + err.message, ["上传课表截图", "手动添加课程"]);
  } finally {
    state.aiChatBusy = false;
  }
}

function renderAnswerModeBadge(response) {
  const mode = response?.answer_mode || response?.answerMode || "";
  const grounding = response?.grounding || {};
  if (mode === "llm_knowledge_hybrid") {
    const label = grounding.knowledge_base
      ? "LLM + 知识库 + 结构化培养方案"
      : "LLM + 结构化培养方案";
    return `<div class="answer-mode-badge hybrid" title="回答由大模型综合检索证据和结构化数据生成">✓ ${label}</div>`;
  }
  if (mode === "knowledge_fallback") {
    return `<div class="answer-mode-badge fallback" title="大模型未配置、被关闭或调用失败，当前展示可核验的本地数据">⚠ 知识库 / 培养方案降级回答</div>`;
  }
  return "";
}

async function exportAiConversation() {
  const messages = state.aiConversation || [];
  if (!messages.length) {
    showToast("当前对话还没有内容，暂时无法导出。", "error");
    return;
  }
  const title = $("#aiConvTitle")?.textContent?.trim() || "勤勉对话";
  const format = $("#aiExportFormat")?.value || "markdown";
  if (format !== "markdown") {
    const button = $("#aiExportConversation");
    button.disabled = true;
    try {
      await downloadServerExport({
        kind: "conversation",
        format,
        title,
        data: {
          user: state.user?.username || "",
          messages: messages.map((item) => ({
            role: item.role,
            content: String(item.content || item.text || ""),
          })),
        },
        fallbackFilename: `${safeFilename(title)}_对话.${format}`,
      });
      showToast(`当前对话已导出为 ${format.toUpperCase()}。`);
    } catch (error) {
      showToast(error.message, "error");
    } finally {
      button.disabled = false;
    }
    return;
  }
  const lines = [
    `# ${title}`,
    "",
    `- 导出时间：${new Date().toLocaleString("zh-CN")}`,
    `- 用户：${state.user?.username || ""}`,
    `- 消息数：${messages.length}`,
    "",
  ];
  for (const item of messages) {
    const role = item.role === "user" ? "用户" : "勤勉 AI";
    const raw = String(item.content || item.text || "");
    const holder = document.createElement("div");
    holder.innerHTML = raw;
    const content = holder.textContent || holder.innerText || raw;
    lines.push(`## ${role}`, "", content.trim(), "");
  }
  downloadText(`${safeFilename(title)}_对话.md`, lines.join("\n"), "text/markdown;charset=utf-8");
  showToast("当前对话已导出为 Markdown 文件。");
}

function clearFileUpload() {
  const filePreview = $("#aiFilePreview");
  const fileInput = $("#aiFileInput");
  if (filePreview) filePreview.style.display = "none";
  if (fileInput) fileInput.value = "";
}

async function sendAiMessage() {
  const input = $("#aiChatInput");
  const message = input.value.trim();
  if (!message || state.aiChatBusy) return;
  const recentHistory = state.aiConversation
    .slice(-12)
    .map((item) => ({ role: item.role, text: item.content || item.text || "" }));

  // 如果没有活跃会话，先创建
  if (!state.activeConvId) {
    await newAiConversation();
  }

  state.aiChatBusy = true;
  input.value = "";

  // 显示用户消息
  state.aiConversation.push({ role: "user", content: message });
  appendAiMessage("user", message);
  // 同步到浮动聊天
  state.chat.push({ role: "user", text: `[AI助手] ${message}` });
  renderFloatingChat();

  // 显示思考中
  showAiThinking();

  const sendBtn = $("#aiChatSend");
  if (sendBtn) sendBtn.disabled = true;

  try {
    const response = await api("/api/chat", {
      method: "POST",
      body: JSON.stringify({
        message,
        conversation_id: state.activeConvId,
        context: {
          persona: state.persona,
          major_id: state.selectedMajor?.id,
          student_type: state.studentType,
          chat_history: recentHistory,
          knowledge_base_enabled: state.memoryEnabled,
        },
      }),
    });

    hideAiThinking();

    const answer = response.answer || "";
    const suggestions = response.suggestions || [];
    const intent = response.intent || "";

    // 检查是否为课表规划结果 → 渲染完整学期时间线
    const extraHtml = renderAnswerModeBadge(response) + renderCareerPlanExtra(response);

    state.aiConversation.push({
      role: "assistant",
      content: answer,
      extraHtml,
      answerMode: response.answer_mode,
      grounding: response.grounding,
    });
    appendAiMessage("assistant", answer, suggestions, extraHtml);
    // 同步到浮动聊天
    state.chat.push({
      role: "assistant",
      text: `[AI助手] ${answer.slice(0, 200)}${answer.length > 200 ? "…" : ""}`,
      answerMode: response.answer_mode,
      grounding: response.grounding,
    });
    renderFloatingChat();

    // AI→Professor sync: 根据意图切换标签页并设置筛选条件
    rememberResponseContext(response);
    if (state.activeTab === "professor") {
      // 重新渲染教授匹配页以应用新筛选条件
      await renderTab();
    }

    // 更新对话标题和计数
    const badge = $("#aiConvBadge");
    if (badge) {
      const count = state.aiConversation.length;
      badge.textContent = `${count} 条`;
    }

    // 更新会话标题
    const titleEl = $("#aiConvTitle");
    if (titleEl && state.aiConversation.length <= 2) {
      titleEl.textContent = message.slice(0, 20) + (message.length > 20 ? "..." : "");
    }

    // 刷新对话列表（后台）
    refreshConversationList();

    // 粒子爆发反馈
    if (state.particleSystem) {
      state.particleSystem.addBurst(
        window.innerWidth * 0.7 + Math.random() * 100,
        window.innerHeight * 0.5,
        8
      );
    }
  } catch (error) {
    hideAiThinking();
    const errMsg = `请求失败：${error.message}`;
    state.aiConversation.push({ role: "assistant", content: errMsg });
    appendAiMessage("assistant", errMsg, ["再试一次", "检查大模型 API 配置"]);
  } finally {
    state.aiChatBusy = false;
    if (sendBtn) sendBtn.disabled = false;
    input.focus();
  }
}

async function refreshConversationList() {
  try {
    const data = await api("/api/conversations");
    state.conversations = data.conversations || [];
    renderConversationList();
  } catch (_) {}
}

// ═════════════════════════════════════════════════════════════════════
// 启动
// ═════════════════════════════════════════════════════════════════════

init().catch((error) => {
  document.body.innerHTML = `<div class="empty-state">勤勉启动失败：${escapeHtml(error.message)}</div>`;
});
