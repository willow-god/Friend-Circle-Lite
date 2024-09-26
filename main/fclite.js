function initialize_fc_lite() {
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
            <div>Powered by: <a href="https://github.com/willow-god/Friend-Circle-Lite" target="_blank" rel="nofollow">FriendCircleLite</a><br></div>
            <div>Designed By: <a href="https://www.liushen.fun/" target="_blank" rel="nofollow">LiuShen</a><br></div>
            <div>订阅:${stats.friends_num}   活跃:${stats.active_num}   总文章数:${stats.article_num}<br></div>
            <div>更新时间:${stats.last_updated_time}</div>
        `;

        // 随机友链卡片
        updateRandomArticle();

        const fragment = document.createDocumentFragment();
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

            const bgImg = document.createElement('img');
            bgImg.className = 'card-bg no-lightbox';
            bgImg.src = article.avatar || UserConfig.error_img;
            bgImg.onerror = () => bgImg.src = UserConfig.error_img; // 头像加载失败时使用默认头像
            card.appendChild(bgImg);

            fragment.appendChild(card);
        });

        container.appendChild(fragment);
        start += UserConfig.page_turning_number;

        if (start >= allArticles.length) {
            loadMoreBtn.style.display = 'none'; // 隐藏按钮
        }
    }

    function updateRandomArticle() {
        const randomArticle = allArticles[Math.floor(Math.random() * allArticles.length)];
        randomArticleContainer.innerHTML = `
            <div class="random-container">
                <div class="random-container-title">
                    <span>🎣 钓鱼</span>
                    <span class="random-refresh" onclick="updateRandomArticle()">
                        <svg t="1721999754997" class="icon" viewBox="0 0 1024 1024" version="1.1" p-id="1207" width="16" height="16"><path d="M772.6 320H672c-35.4 0-64 28.6-64 64s28.6 64 64 64h256c35.4 0 64-28.6 64-64V128c0-35.4-28.6-64-64-64s-64 28.6-64 64v102.4l-35.2-35.2c-175-175-458.6-175-633.6 0s-175 458.6 0 633.6 458.6 175 633.6 0c25-25 25-65.6 0-90.6s-65.6-25-90.6 0c-125 125-327.6 125-452.6 0s-125-327.6 0-452.6 327.6-125 452.6 0l34.4 34.4z" p-id="1208"></path></svg>
                    </span>
                </div>
                <div class="random-title">${randomArticle.title}</div>
                <div class="random-author">作者: ${randomArticle.author}</div>
            </div>
            <button class="random-link-button" onclick="window.open('${randomArticle.link}', '_blank')">过去转转</button>
        `;
    }

    function showAuthorArticles(author, avatar, link) {
        // 如果不存在，则创建模态框结构
        if (!document.getElementById('modal')) {
            const modal = document.createElement('div');
            modal.id = 'modal';
            modal.className = 'modal';
            modal.innerHTML = `
            <div class="modal-content">
                <img id="modal-author-avatar" src="" alt="">
                <a id="modal-author-name-link"></a>
                <div id="modal-articles-container"></div>
                <img class="modal-background" src="" alt="">
            </div>
            `;
            document.body.appendChild(modal);
        }

        const modal = document.getElementById('modal');
        const modalArticlesContainer = document.getElementById('modal-articles-container');
        const modalAuthorAvatar = document.getElementById('modal-author-avatar');
        const modalAuthorNameLink = document.getElementById('modal-author-name-link');
        const modalBackground = document.querySelector('.modal-background');

        modalArticlesContainer.innerHTML = ''; // 清空之前的内容
        modalAuthorAvatar.src = avatar  || UserConfig.error_img; // 使用默认头像
        modalAuthorAvatar.onerror = () => modalAuthorAvatar.src = UserConfig.error_img; // 头像加载失败时使用默认头像
        modalAuthorNameLink.innerText = author;
        modalAuthorNameLink.href = new URL(link).origin;

        // 设置背景图
        modalBackground.src = avatar || UserConfig.error_img;
        modalBackground.onerror = () => modalBackground.src = UserConfig.error_img; // 头像加载失败时使用默认头像

        const authorArticles = allArticles.filter(article => article.author === author);
        // 仅仅取前五个，防止文章过多导致模态框过长，如果不够五个则全部取出
        authorArticles.slice(0, 5).forEach(article => {
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
            document.body.removeChild(modal);
        }, { once: true });
    }

    // 初始加载
    loadMoreArticles();

    // 加载更多按钮点击事件
    loadMoreBtn.addEventListener('click', loadMoreArticles);

    // 添加刷新按钮点击事件
    window.updateRandomArticle = updateRandomArticle;

    // 点击遮罩层关闭模态框
    window.onclick = function(event) {
        const modal = document.getElementById('modal');
        if (event.target === modal) {
            hideModal();
        }
    };
}

document.addEventListener("DOMContentLoaded", function() {
    setTimeout(initialize_fc_lite, 0);
});

document.addEventListener('pjax:complete', function() {
    setTimeout(initialize_fc_lite, 0);
});

setTimeout(initialize_fc_lite, 0);