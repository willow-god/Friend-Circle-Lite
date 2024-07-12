document.addEventListener("DOMContentLoaded", function () {
    const container = document.getElementById('articles-container');
    let start = 0;
    const batchSize = 20; // 每次加载的卡片数量

    function loadMoreArticles() {
        fetch('https://fc.liushen.fun/all.json')
            .then(response => response.json())
            .then(data => {
                allArticles = data.article_data;
                const randomArticle = allArticles[Math.floor(Math.random() * allArticles.length)];
                const articles = data.article_data.slice(start, start + batchSize);
                const randomArticleElement = document.getElementById('random-article');

                randomArticleElement.innerHTML = `
                <div class="random-container">
                    <div class="random-container-title">随机钓鱼</div>
                    <div class="random-title">${randomArticle.title}</div>
                    <div class="random-author">作者: ${randomArticle.author}</div>
                </div>
                <button class="random-link-button" onclick="window.open('${randomArticle.link}', '_blank')">过去转转</button>
                `;

                articles.forEach(article => {
                    const card = document.createElement('div');
                    card.className = 'card';

                    const title = document.createElement('div');
                    title.className = 'card-title';
                    title.innerText = article.title;
                    card.appendChild(title);

                    title.onclick = () => {
                        window.open(article.link, '_blank');
                    };

                    const author = document.createElement('div');
                    author.className = 'card-author';
                    const authorImg = document.createElement('img');
                    authorImg.src = article.avatar;
                    author.appendChild(authorImg);
                    author.appendChild(document.createTextNode(article.author));
                    card.appendChild(author);

                    author.onclick = () => {
                        showAuthorArticles(article.author, article.avatar, article.link);
                    };

                    const date = document.createElement('div');
                    date.className = 'card-date';
                    date.appendChild(document.createTextNode(article.created.substring(0, 10)));
                    card.appendChild(date);

                    const bgImg = document.createElement('img');
                    bgImg.className = 'card-bg';
                    bgImg.src = article.avatar;
                    card.appendChild(bgImg);

                    container.appendChild(card);
                });

                start += batchSize;

                if (start >= data.article_data.length) {
                    // 如果加载完所有卡片，隐藏加载更多按钮
                    document.getElementById('load-more-btn').style.display = 'none';
                }
            });
    }

    // 显示作者文章的函数
    function showAuthorArticles(author, avatar, link) {
        const modal = document.getElementById('modal');
        const modalArticlesContainer = document.getElementById('modal-articles-container');
        const modalAuthorAvatar = document.getElementById('modal-author-avatar');
        const modalAuthorNameLink = document.getElementById('modal-author-name-link');

        modalArticlesContainer.innerHTML = ''; // 清空之前的内容
        modalAuthorAvatar.src = avatar;
        modalAuthorNameLink.innerText = author;
        modalAuthorNameLink.href = new URL(link).origin;

        const authorArticles = allArticles.filter(article => article.author === author);
        authorArticles.forEach(article => {
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
            date.innerText = "--" + article.created.substring(0, 10);
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
        }, { once: true });
    }
    
    // 初始加载
    loadMoreArticles();

    // 加载更多按钮点击事件
    document.getElementById('load-more-btn').addEventListener('click', loadMoreArticles);

    // 点击遮罩层关闭模态框
    window.onclick = function(event) {
        const modal = document.getElementById('modal');
        if (event.target === modal) {
            hideModal();
        }
    };
});
