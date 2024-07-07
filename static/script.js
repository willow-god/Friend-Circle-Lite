document.addEventListener("DOMContentLoaded", function () {
    const container = document.getElementById('articles-container');
    let start = 0;
    const batchSize = 20; // 每次加载的卡片数量

    function loadMoreArticles() {
        fetch('./all.json')
            .then(response => response.json())
            .then(data => {
                const articles = data.article_data.slice(start, start + batchSize);
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

                    const date = document.createElement('div');
                    date.className = 'card-date';
                    const dateImg = document.createElement('img');
                    dateImg.src = './static/img/rili.png';  // 替换为实际的图标路径
                    date.appendChild(dateImg);
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

    // 初始加载
    loadMoreArticles();

    // 加载更多按钮点击事件
    document.getElementById('load-more-btn').addEventListener('click', loadMoreArticles);
});
