// script.js
document.addEventListener('DOMContentLoaded', function() {
    // إضافة تأثيرات للعناصر
    const addHoverEffects = () => {
        const cards = document.querySelectorAll('.stat-card, .section-card');
        cards.forEach(card => {
            card.addEventListener('mouseenter', () => {
                card.style.transform = 'translateY(-5px)';
                card.style.boxShadow = '0 8px 25px rgba(0,0,0,0.15)';
            });
            
            card.addEventListener('mouseleave', () => {
                card.style.transform = 'translateY(0)';
                card.style.boxShadow = '0 4px 15px rgba(0,0,0,0.08)';
            });
        });
    };

    // إدارة التنبيهات
    const setupAlerts = () => {
        const closeButtons = document.querySelectorAll('.close-btn');
        closeButtons.forEach(btn => {
            btn.addEventListener('click', function() {
                this.parentElement.style.opacity = '0';
                setTimeout(() => {
                    this.parentElement.remove();
                }, 300);
            });
        });

        // إخفاء التنبيهات تلقائياً بعد 5 ثوان
        const alerts = document.querySelectorAll('.alert');
        alerts.forEach(alert => {
            setTimeout(() => {
                alert.style.opacity = '0';
                setTimeout(() => alert.remove(), 300);
            }, 5000);
        });
    };

    // تحسين تجربة النماذج
    const enhanceForms = () => {
        const inputs = document.querySelectorAll('input, select, textarea');
        inputs.forEach(input => {
            input.addEventListener('focus', function() {
                this.parentElement.classList.add('focused');
            });
            
            input.addEventListener('blur', function() {
                this.parentElement.classList.remove('focused');
            });
        });
    };

    // تهيئة جميع الوظائف
    addHoverEffects();
    setupAlerts();
    enhanceForms();

    // تحميل البيانات الديناميكية
    if (typeof loadDynamicData === 'function') {
        loadDynamicData();
    }
});

// وظائف مساعدة
function showLoading() {
    const loader = document.createElement('div');
    loader.className = 'loading-overlay';
    loader.innerHTML = `
        <div class="loading-spinner">
            <i class="fas fa-spinner fa-spin"></i>
            <p>جاري التحميل...</p>
        </div>
    `;
    document.body.appendChild(loader);
}

function hideLoading() {
    const loader = document.querySelector('.loading-overlay');
    if (loader) {
        loader.remove();
    }
}

// إدارة الطلبات AJAX
async function apiRequest(url, options = {}) {
    showLoading();
    try {
        const response = await fetch(url, {
            headers: {
                'Content-Type': 'application/json',
                ...options.headers
            },
            ...options
        });
        
        const data = await response.json();
        hideLoading();
        return data;
    } catch (error) {
        hideLoading();
        showNotification('حدث خطأ في الاتصال', 'error');
        throw error;
    }
}

function showNotification(message, type = 'info') {
    const notification = document.createElement('div');
    notification.className = `notification notification-${type}`;
    notification.innerHTML = `
        <span>${message}</span>
        <button onclick="this.parentElement.remove()">×</button>
    `;
    
    document.body.appendChild(notification);
    
    setTimeout(() => {
        notification.remove();
    }, 5000);
}

// إضافة أنماط إضافية ديناميكياً
const additionalStyles = `
.loading-overlay {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background: rgba(255,255,255,0.9);
    display: flex;
    justify-content: center;
    align-items: center;
    z-index: 9999;
}

.loading-spinner {
    text-align: center;
    color: var(--primary-color);
}

.loading-spinner i {
    font-size: 3rem;
    margin-bottom: 1rem;
}

.notification {
    position: fixed;
    top: 20px;
    right: 20px;
    padding: 1rem 1.5rem;
    border-radius: 8px;
    color: white;
    z-index: 10000;
    display: flex;
    align-items: center;
    gap: 1rem;
    animation: slideIn 0.3s ease-out;
}

.notification-info { background: var(--info-color); }
.notification-success { background: var(--success-color); }
.notification-error { background: var(--danger-color); }
.notification-warning { background: var(--warning-color); }

@keyframes slideIn {
    from {
        transform: translateX(100%);
        opacity: 0;
    }
    to {
        transform: translateX(0);
        opacity: 1;
    }
}

.form-group.focused label {
    color: var(--primary-color);
}

.form-group.focused input {
    border-color: var(--primary-color);
}
`;

const styleSheet = document.createElement('style');
styleSheet.textContent = additionalStyles;
document.head.appendChild(styleSheet);