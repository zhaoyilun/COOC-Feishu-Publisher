const grid = document.querySelector('#course-grid');
const status = document.querySelector('#data-status');
const generatedAt = document.querySelector('#generated-at');

function text(value) {
  return typeof value === 'string' ? value : '';
}

function renderCourse(course) {
  const card = document.createElement('article');
  card.className = 'course-card';

  const category = document.createElement('span');
  category.className = 'category';
  category.textContent = text(course.category) || '公开课程';

  const title = document.createElement('h3');
  title.textContent = text(course.title);

  const summary = document.createElement('p');
  summary.textContent = text(course.summary) || '课程资料正在持续建设。';

  const footer = document.createElement('div');
  footer.className = 'card-footer';
  const updated = document.createElement('span');
  updated.textContent = text(course.updated_at) ? `更新：${course.updated_at}` : '持续更新';
  footer.append(updated);

  if (text(course.document_url)) {
    const link = document.createElement('a');
    link.className = 'document-link';
    link.href = course.document_url;
    link.target = '_blank';
    link.rel = 'noopener noreferrer';
    link.textContent = '阅读资料';
    footer.append(link);
  } else {
    const unavailable = document.createElement('span');
    unavailable.className = 'unavailable';
    unavailable.textContent = '资料准备中';
    footer.append(unavailable);
  }

  card.append(category, title, summary, footer);
  return card;
}

async function loadCatalogue() {
  try {
    const response = await fetch('./data/courses.json', { cache: 'no-store' });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const catalogue = await response.json();
    const courses = Array.isArray(catalogue.courses) ? catalogue.courses : [];
    status.textContent = `已加载 ${courses.length} 门公开课程`;
    generatedAt.textContent = text(catalogue.generated_at) ? `数据生成：${catalogue.generated_at}` : '';
    if (!courses.length) {
      grid.innerHTML = '<p class="empty">暂未发布公开课程。</p>';
      return;
    }
    grid.replaceChildren(...courses.map(renderCourse));
  } catch {
    status.textContent = '公开课程目录暂不可用，请稍后重试。';
    grid.innerHTML = '<p class="empty">未能加载课程数据。</p>';
  }
}

loadCatalogue();
