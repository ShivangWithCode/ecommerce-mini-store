/**
 * Instant Search, Category Filter & Price Sorting
 * Powered by Fetch API with automatic debouncing and URL sync
 */
document.addEventListener('DOMContentLoaded', () => {
    const searchInput = document.getElementById('search-input');
    const searchClearBtn = document.getElementById('search-clear-btn');
    const categorySelect = document.getElementById('category-select');
    const sortSelect = document.getElementById('sort-select');
    const productGrid = document.getElementById('product-grid');
    const emptyState = document.getElementById('empty-state');
    const resultsCount = document.getElementById('results-count');
    const resetFiltersBtn = document.getElementById('btn-clear-filters');
    const emptyClearBtn = document.getElementById('empty-clear-btn');
    const filterForm = document.getElementById('filter-form');

    if (!searchInput || !productGrid) return;

    // Prevent default form submit on Enter key, trigger instant fetch instead
    if (filterForm) {
        filterForm.addEventListener('submit', (e) => {
            e.preventDefault();
            fetchProducts();
        });
    }

    let debounceTimer = null;

    function renderStockBadge(stock) {
        if (stock === null || stock === undefined || stock <= 0) {
            return '<span class="stock-badge stock-out">Out of Stock</span>';
        } else if (stock <= 5) {
            return `<span class="stock-badge stock-low">Only ${stock} left!</span>`;
        } else {
            return `<span class="stock-badge stock-in">In Stock (${stock})</span>`;
        }
    }

    function renderProducts(products) {
        if (!products || products.length === 0) {
            productGrid.style.display = 'none';
            if (emptyState) emptyState.style.display = 'block';
            if (resultsCount) resultsCount.textContent = 'No products found';
            return;
        }

        if (emptyState) emptyState.style.display = 'none';
        productGrid.style.display = 'grid';

        if (resultsCount) {
            const count = products.length;
            resultsCount.textContent = `Showing ${count} product${count === 1 ? '' : 's'}`;
        }

        const cardsHtml = products.map((p) => {
            const imgPath = `/static/images/${p.image_url || 'bag.jpg'}`;
            return `
                <div class="product-card" id="card-prod-${p.id}">
                    <a href="${p.detail_url}">
                        <img src="${imgPath}" alt="${escapeHtml(p.name)}" onerror="this.src='/static/images/bag.jpg'">
                    </a>
                    <h3><a href="${p.detail_url}">${escapeHtml(p.name)}</a></h3>
                    <p class="price">₹${p.formatted_price || p.price}</p>
                    <span class="category-badge">${escapeHtml(p.category || 'General')}</span>
                    <div style="margin-top: 8px;">
                        ${renderStockBadge(p.stock)}
                    </div>
                </div>
            `;
        }).join('');

        productGrid.innerHTML = cardsHtml;
    }

    function escapeHtml(text) {
        if (!text) return '';
        const map = {
            '&': '&amp;',
            '<': '&lt;',
            '>': '&gt;',
            '"': '&quot;',
            "'": '&#039;'
        };
        return String(text).replace(/[&<>"']/g, (m) => map[m]);
    }

    function updateControlButtons(search, category, sort) {
        if (searchClearBtn) {
            searchClearBtn.style.display = search ? 'block' : 'none';
        }
        if (resetFiltersBtn) {
            const isDefault = !search && !category && (!sort || sort === 'newest');
            resetFiltersBtn.style.display = isDefault ? 'none' : 'inline-block';
        }
    }

    function updateUrlParams(search, category, sort) {
        const url = new URL(window.location);
        if (search) url.searchParams.set('search', search);
        else url.searchParams.delete('search');

        if (category) url.searchParams.set('category', category);
        else url.searchParams.delete('category');

        if (sort && sort !== 'newest') url.searchParams.set('sort', sort);
        else url.searchParams.delete('sort');

        window.history.replaceState({}, '', url);
    }

    function fetchProducts() {
        const search = searchInput.value.trim();
        const category = categorySelect ? categorySelect.value : '';
        const sort = sortSelect ? sortSelect.value : 'newest';

        updateControlButtons(search, category, sort);
        updateUrlParams(search, category, sort);

        const params = new URLSearchParams();
        if (search) params.append('search', search);
        if (category) params.append('category', category);
        if (sort) params.append('sort', sort);

        // Add subtle loading opacity
        productGrid.style.opacity = '0.6';

        fetch(`/api/products?${params.toString()}`)
            .then((res) => {
                if (!res.ok) throw new Error(`HTTP error ${res.status}`);
                return res.json();
            })
            .then((data) => {
                productGrid.style.opacity = '1';
                renderProducts(data.products);
            })
            .catch((err) => {
                productGrid.style.opacity = '1';
                console.error('Failed to fetch filtered products:', err);
            });
    }

    // Debounced input on typing
    searchInput.addEventListener('input', () => {
        clearTimeout(debounceTimer);
        debounceTimer = setTimeout(fetchProducts, 250);
    });

    // Instant change on selectors
    if (categorySelect) {
        categorySelect.addEventListener('change', fetchProducts);
    }

    if (sortSelect) {
        sortSelect.addEventListener('change', fetchProducts);
    }

    // Clear search text
    if (searchClearBtn) {
        searchClearBtn.addEventListener('click', () => {
            searchInput.value = '';
            searchInput.focus();
            fetchProducts();
        });
    }

    // Reset all filters
    function resetAllFilters(e) {
        if (e) e.preventDefault();
        searchInput.value = '';
        if (categorySelect) categorySelect.value = '';
        if (sortSelect) sortSelect.value = 'newest';
        fetchProducts();
    }

    if (resetFiltersBtn) {
        resetFiltersBtn.addEventListener('click', resetAllFilters);
    }

    if (emptyClearBtn) {
        emptyClearBtn.addEventListener('click', resetAllFilters);
    }
});
