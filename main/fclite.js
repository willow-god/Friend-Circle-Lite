function initialize_fc_lite() {

    // 用户配置
    // 设置默认配置
    UserConfig = {
        private_api_url: UserConfig?.private_api_url || "", 
        page_turning_number: UserConfig?.page_turning_number || 24, // 默认24篇
        error_img: UserConfig?.error_img || "https://fastly.jsdelivr.net/gh/willow-god/Friend-Circle-Lite/static/favicon.ico" // 默认头像
    };

    const root = document.getElementById('friend-circle-lite-root');
    
    if (!root) return; // 确保根元素存在

    // 清除之前的内容
    root.innerHTML = '';

    const randomArticleContainer = document.createElement('div');
    randomArticleContainer.id = 'random-article';
    root.appendChild(randomArticleContainer);

    const container = document.createElement('div');
    container.className = 'articles-container';
    container.id = 'articles-container';
    root.appendChild(container);
    
    const loadMoreBtn = document.createElement('button');
    loadMoreBtn.id = 'load-more-btn';
    loadMoreBtn.innerText = '再来亿点';
    root.appendChild(loadMoreBtn);

    // 创建统计信息容器
    const statsContainer = document.createElement('div');
    statsContainer.id = 'stats-container';
    root.appendChild(statsContainer);

    let start = 0; // 记录加载起始位置
    let allArticles = []; // 存储所有文章
    // 友链状态索引：host -> { state, latency, failCount, hasAuthorLink }
    let linkStatusMap = new Map();

    // 取 URL 主机名并归一化（去 www. 前缀，转小写）
    function getHost(url) {
        try {
            return new URL(url).hostname.toLowerCase().replace(/^www\./, '');
        } catch (e) {
            return '';
        }
    }

    // 异步加载友链状态检测结果；失败/缺失/异常统一返回空 Map
    async function loadLinkStatus() {
        try {
            const res = await fetch(`${UserConfig.private_api_url}result.json`, { cache: 'no-cache' });
            if (!res.ok) return;
            const data = await res.json();
            if (!data || !Array.isArray(data.link_status)) return;
            data.link_status.forEach(item => {
                const host = getHost(item.link || '');
                if (!host) return;
                let state = 'unknown';
                const latency = Number(item.latency);
                if (latency === -1) {
                    state = 'fail';
                } else if (Number.isFinite(latency) && latency >= 0) {
                    state = latency < 0.3 ? 'ok' : 'warn';
                }
                linkStatusMap.set(host, {
                    state,
                    latency,
                    failCount: Number.isFinite(Number(item.fail_count)) ? Number(item.fail_count) : 0,
                    hasAuthorLink: item.has_author_link === true
                });
            });
        } catch (e) {
            // 静默吞错，所有卡片走 unknown 分支
            linkStatusMap = new Map();
        }
    }

    // 取作者 host：优先 article.link，否则用 avatar 所在域
    function getArticleHost(article) {
        const linkHost = getHost(article.link || '');
        if (linkHost) return linkHost;
        return getHost(article.avatar || '');
    }

    // 构造右上角状态点 DOM
    function buildStatusBadge(status) {
        const wrap = document.createElement('div');
        wrap.className = `card-status card-status--${status.state}`;
        const dot = document.createElement('span');
        dot.className = `card-status-dot card-status-dot--${status.state}`;
        const text = document.createElement('span');
        text.className = 'card-status-text';
        if (status.state === 'fail') {
            text.textContent = '超时';
        } else if (status.state === 'unknown') {
            text.textContent = '未知';
        } else {
            text.textContent = `${Math.round(status.latency * 1000)}ms`;
        }
        wrap.appendChild(dot);
        wrap.appendChild(text);
        return wrap;
    }

    // 构造行内元信息 DOM
    function buildMetaLine(status) {
        const meta = document.createElement('div');
        meta.className = 'card-meta';

        const date = document.createElement('span');
        date.className = 'card-meta-date';
        date.textContent = '🗓️';
        meta.appendChild(date);

        const sep = document.createElement('span');
        sep.className = 'card-meta-sep';
        sep.textContent = '·';
        meta.appendChild(sep);

        let badgeText = '未检测';
        let badgeState = 'unknown';
        if (status.state !== 'unknown') {
            badgeState = status.hasAuthorLink ? 'ok' : 'fail';
            badgeText = status.hasAuthorLink ? '已反链' : '未反链';
        }
        const badge = document.createElement('span');
        badge.className = `card-meta-badge card-meta-badge--${badgeState}`;
        badge.textContent = badgeText;
        meta.appendChild(badge);

        if (status.failCount >= 1) {
            const fail = document.createElement('span');
            fail.className = 'card-meta-fail';
            fail.textContent = `失败 ${status.failCount} 次`;
            meta.appendChild(fail);
        }

        return meta;
    }

    function loadMoreArticles() {
        const cacheKey = 'friend-circle-lite-cache';
        const cacheTimeKey = 'friend-circle-lite-cache-time';
        const cacheTime = localStorage.getItem(cacheTimeKey);
        const now = new Date().getTime();

        if (cacheTime && (now - cacheTime < 10 * 60 * 1000)) { // 缓存时间小于10分钟
            const cachedData = JSON.parse(localStorage.getItem(cacheKey));
            if (cachedData) {
                processArticles(cachedData);
                return;
            }
        }

        fetch(`${UserConfig.private_api_url}all.json`)
            .then(response => response.json())
            .then(data => {
                localStorage.setItem(cacheKey, JSON.stringify(data));
                localStorage.setItem(cacheTimeKey, now.toString());
                processArticles(data);
            })
            .finally(() => {
                loadMoreBtn.innerText = '再来亿点'; // 恢复按钮文本
            });
    }

    function processArticles(data) {
        allArticles = data.article_data;
        // 处理统计数据
        const stats = data.statistical_data;
        statsContainer.innerHTML = `
            <div>Powered by: <a href="https://github.com/willow-god/Friend-Circle-Lite" target="_blank">FriendCircleLite</a><br></div>
            <div>Designed By: <a href="https://www.liushen.fun/" target="_blank">LiuShen</a><br></div>
            <div>订阅:${stats.friends_num}   活跃:${stats.active_num}   总文章数:${stats.article_num}<br></div>
            <div>更新时间:${stats.last_updated_time}</div>
        `;

        displayRandomArticle(); // 显示随机友链卡片

        const articles = allArticles.slice(start, start + UserConfig.page_turning_number);

        articles.forEach(article => {
            const card = document.createElement('div');
            card.className = 'card';

            const title = document.createElement('div');
            title.className = 'card-title';
            title.innerText = article.title;
            card.appendChild(title);
            title.onclick = () => window.open(article.link, '_blank');

            const author = document.createElement('div');
            author.className = 'card-author';
            const authorImg = document.createElement('img');
            authorImg.className = 'no-lightbox';
            authorImg.referrerPolicy = 'no-referrer-when-downgrade';
            authorImg.src = article.avatar || UserConfig.error_img; // 使用默认头像
            authorImg.onerror = () => authorImg.src = UserConfig.error_img; // 头像加载失败时使用默认头像
            author.appendChild(authorImg);
            author.appendChild(document.createTextNode(article.author));
            card.appendChild(author);

            author.onclick = () => {
                showAuthorArticles(article.author, article.avatar, article.link);
            };

            const date = document.createElement('div');
            date.className = 'card-date';
            date.innerText = "🗓️" + article.created.substring(0, 10);
            card.appendChild(date);

            // 友链状态融合：右上角状态点 + 行内元信息
            const host = getArticleHost(article);
            const status = linkStatusMap.get(host) || { state: 'unknown', latency: -1, failCount: 0, hasAuthorLink: false };
            card.appendChild(buildStatusBadge(status));
            card.appendChild(buildMetaLine(status));

            const bgImg = document.createElement('img');
            bgImg.className = 'card-bg no-lightbox';
            bgImg.referrerPolicy = 'no-referrer-when-downgrade';
            bgImg.src = article.avatar || UserConfig.error_img;
            bgImg.onerror = () => bgImg.src = UserConfig.error_img; // 头像加载失败时使用默认头像
            card.appendChild(bgImg);

            container.appendChild(card);
        });

        start += UserConfig.page_turning_number;

        if (start >= allArticles.length) {
            loadMoreBtn.style.display = 'none'; // 隐藏按钮
        }
    }

    // 显示随机文章的逻辑
    function displayRandomArticle() {
        const randomArticle = allArticles[Math.floor(Math.random() * allArticles.length)];
        randomArticleContainer.innerHTML = `
            <div class="random-container">
                <div class="random-container-title">随机钓鱼</div>
                <div class="random-title">${randomArticle.title}</div>
                <div class="random-author">作者: ${randomArticle.author}</div>
            </div>
            <div class="random-button-container">
                <a href="#" id="refresh-random-article">刷新</a>
                <button class="random-link-button" onclick="window.open('${randomArticle.link}', '_blank')">过去转转</button>
            </div>
        `;

        // 为刷新按钮添加事件监听器
        const refreshBtn = document.getElementById('refresh-random-article');
        refreshBtn.addEventListener('click', function (event) {
            event.preventDefault(); // 阻止默认的跳转行为
            displayRandomArticle(); // 调用显示随机文章的逻辑
        });
    }

    function showAuthorArticles(author, avatar, link) {
        // 如果不存在，则创建模态框结构
        if (!document.getElementById('fclite-modal')) {
            const modal = document.createElement('div');
            modal.id = 'modal';
            modal.className = 'modal';
            modal.innerHTML = `
            <div class="modal-content">
                <img id="modal-author-avatar" src="" alt="">
                <a id="modal-author-name-link"></a>
                <div id="modal-articles-container"></div>
                <img id="modal-bg" src="" alt="">
            </div>
            `;
            root.appendChild(modal);
        }

        const modal = document.getElementById('modal');
        const modalArticlesContainer = document.getElementById('modal-articles-container');
        const modalAuthorAvatar = document.getElementById('modal-author-avatar');
        const modalAuthorNameLink = document.getElementById('modal-author-name-link');
        const modalBg = document.getElementById('modal-bg');

        modalArticlesContainer.innerHTML = ''; // 清空之前的内容
        modalAuthorAvatar.referrerPolicy = 'no-referrer-when-downgrade';
        modalAuthorAvatar.src = avatar  || UserConfig.error_img; // 使用默认头像
        modalAuthorAvatar.onerror = () => modalAuthorAvatar.src = UserConfig.error_img; // 头像加载失败时使用默认头像
        modalBg.referrerPolicy = 'no-referrer-when-downgrade';
        modalBg.src = avatar || UserConfig.error_img; // 使用默认头像
        modalBg.onerror = () => modalBg.src = UserConfig.error_img; // 头像加载失败时使用默认头像
        modalAuthorNameLink.innerText = author;
        modalAuthorNameLink.href = new URL(link).origin;

        const authorArticles = allArticles.filter(article => article.author === author);
        // 仅仅取前五个，防止文章过多导致模态框过长，如果不够五个则全部取出
        authorArticles.slice(0, 4).forEach(article => {
            const articleDiv = document.createElement('div');
            articleDiv.className = 'modal-article';

            const title = document.createElement('a');
            title.className = 'modal-article-title';
            title.innerText = article.title;
            title.href = article.link;
            title.target = '_blank';
            articleDiv.appendChild(title);

            const date = document.createElement('div');
            date.className = 'modal-article-date';
            date.innerText = "📅" + article.created.substring(0, 10);
            articleDiv.appendChild(date);

            modalArticlesContainer.appendChild(articleDiv);
        });

        // 设置类名以触发显示动画
        modal.style.display = 'block';
        setTimeout(() => {
            modal.classList.add('modal-open');
        }, 10); // 确保显示动画触发
    }

    // 隐藏模态框的函数
    function hideModal() {
        const modal = document.getElementById('modal');
        modal.classList.remove('modal-open');
        modal.addEventListener('transitionend', () => {
            modal.style.display = 'none';
            root.removeChild(modal);
        }, { once: true });
    }

    // 初始加载：先等友链状态，再拉文章；后续点击"再来亿点"跳过状态等待
    loadLinkStatus().then(() => loadMoreArticles());

    // 加载更多按钮点击事件
    loadMoreBtn.addEventListener('click', loadMoreArticles);
    
    // 点击遮罩层关闭模态框
    window.onclick = function(event) {
        const modal = document.getElementById('modal');
        if (event.target === modal) {
            hideModal();
        }
    };
};

function whenDOMReady() {
    initialize_fc_lite();
}

whenDOMReady();
document.addEventListener("pjax:complete", initialize_fc_lite);