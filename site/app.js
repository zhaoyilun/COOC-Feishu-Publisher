const stream = document.querySelector('#course-stream');
const gallery = document.querySelector('#gallery-grid');
const categoryList = document.querySelector('#category-list');
const status = document.querySelector('#data-status');
const generatedAt = document.querySelector('#generated-at');
const galleryToggle = document.querySelector('#gallery-toggle');
let allCourses = [];
let activeCategory = '';

function text(value) {
  return typeof value === 'string' ? value : '';
}

function displayDate(value) {
  return text(value).replaceAll('-', '.') || '持续更新';
}

function courseLink(course) {
  return text(course.course_url) || '#course-list';
}

function galleryItem(course) {
  const link = document.createElement('a');
  link.className = 'gallery-item';
  link.href = courseLink(course);
  link.setAttribute('aria-label', `查看课程：${text(course.title)}`);

  if (text(course.cover_url)) {
    const image = document.createElement('img');
    image.src = text(course.cover_url);
    image.alt = `${text(course.title)} 课程封面`;
    image.loading = 'lazy';
    link.append(image);
  } else {
    const placeholder = document.createElement('span');
    placeholder.className = 'gallery-placeholder';
    placeholder.textContent = text(course.title).slice(0, 24);
    link.append(placeholder);
  }

  const label = document.createElement('span');
  label.className = 'gallery-label';
  label.textContent = text(course.title);
  link.append(label);
  return link;
}

function courseArticle(course) {
  const article = document.createElement('article');
  article.className = 'course-panel panel';

  const heading = document.createElement('div');
  heading.className = 'panel-heading';
  heading.textContent = '精选课程';

  const body = document.createElement('div');
  body.className = 'panel-body';
  const title = document.createElement('h3');
  const titleLink = document.createElement('a');
  titleLink.href = courseLink(course);
  titleLink.textContent = text(course.title) || '未命名课程';
  title.append(titleLink);

  const metadata = document.createElement('p');
  metadata.className = 'article-meta';
  metadata.textContent = `发布于 ${displayDate(course.published_at)}  ·  ${text(course.category) || '公开课程'}`;

  const summary = document.createElement('p');
  summary.className = 'article-summary';
  summary.textContent = text(course.summary) || '课程资料正在持续建设。';
  body.append(title, metadata, summary);

  const footer = document.createElement('div');
  footer.className = 'panel-footer';
  const tag = document.createElement('span');
  tag.className = 'article-category';
  tag.textContent = text(course.category) || '公开课程';
  const link = document.createElement('a');
  link.className = 'read-more';
  link.href = courseLink(course);
  link.textContent = '阅读全文';
  footer.append(tag, link);

  article.append(heading, body, footer);
  return article;
}

function filteredCourses() {
  return activeCategory ? allCourses.filter(course => text(course.category) === activeCategory) : allCourses;
}

function renderCourses() {
  const courses = filteredCourses();
  if (!courses.length) {
    stream.innerHTML = '<p class="empty">该分类暂未发布课程。</p>';
    return;
  }
  stream.replaceChildren(...courses.map(courseArticle));
}

function renderCategories() {
  const counts = new Map();
  allCourses.forEach(course => {
    const category = text(course.category) || '公开课程';
    counts.set(category, (counts.get(category) || 0) + 1);
  });
  const entries = [['全部课程', allCourses.length], ...[...counts.entries()].sort((left, right) => left[0].localeCompare(right[0], 'zh-CN'))];
  categoryList.replaceChildren(...entries.map(([name, count]) => {
    const button = document.createElement('button');
    const selected = name === '全部课程' ? !activeCategory : activeCategory === name;
    button.className = selected ? 'category-filter is-active' : 'category-filter';
    button.type = 'button';
    button.innerHTML = `<span>${name}</span><b>${count}</b>`;
    button.addEventListener('click', () => {
      activeCategory = name === '全部课程' ? '' : name;
      renderCategories();
      renderCourses();
    });
    return button;
  }));
}

function renderGallery() {
  const galleryCourses = allCourses.slice(0, 20);
  gallery.replaceChildren(...galleryCourses.map(galleryItem));
}

async function loadCatalogue() {
  try {
    const response = await fetch('./data/courses.json', {cache: 'no-store'});
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const catalogue = await response.json();
    allCourses = Array.isArray(catalogue.courses) ? catalogue.courses : [];
    status.textContent = `已加载 ${allCourses.length} 门公开课程`;
    generatedAt.textContent = text(catalogue.generated_at) ? `数据生成：${text(catalogue.generated_at)}` : '';
    renderGallery();
    renderCategories();
    renderCourses();
  } catch {
    status.textContent = '公开课程目录暂不可用，请稍后重试。';
    stream.innerHTML = '<p class="empty">未能加载课程数据。</p>';
  }
}

galleryToggle.addEventListener('click', () => {
  const expanded = gallery.classList.toggle('is-expanded');
  galleryToggle.setAttribute('aria-expanded', String(expanded));
  galleryToggle.textContent = expanded ? '收起课程展示' : '展开课程展示';
});

loadCatalogue();
