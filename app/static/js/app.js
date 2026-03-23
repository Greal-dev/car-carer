// --- Safe fetch wrapper with timeout and error handling (T-D02) ---
async function safeFetch(url, options = {}) {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 30000);
    try {
        const res = await fetch(url, { ...options, signal: controller.signal });
        clearTimeout(timeout);
        return res;
    } catch (e) {
        clearTimeout(timeout);
        if (e.name === 'AbortError') throw new Error('Requête expirée (30s)');
        throw e;
    }
}

function app() {
    return {
        // Auth state
        authenticated: false,
        currentUser: null,
        authView: 'login', // 'login' or 'register'
        authEmail: '',
        authPassword: '',
        authError: '',
        authLoading: false,

        // App state
        view: 'vehicles',
        vehicles: [],
        selectedVehicle: null,
        showAddVehicle: false,
        showEditVehicle: false,
        newVehicle: { name: '' },
        editVehicleData: {},
        detailTab: 'analysis',
        maintenanceEvents: [],
        ctReports: [],
        documents: [],
        uploadDocType: 'auto',
        uploading: false,
        uploadResult: null,
        dragOver: false,
        batchProgress: null,
        batchResults: [],
        batchEventSource: null,

        // File preview state
        selectedFiles: [],

        // Date clarification
        pendingDocs: [],
        showClarifyModal: false,
        clarifyDoc: null,
        clarifyDate: '',

        // Analysis state
        analysis: null,
        analysisLoading: false,
        stats: null,
        statsLoading: false,

        // Sprint 4: Filters
        maintenanceFilter: { q: '', event_type: '', date_from: '', date_to: '' },
        filteredMaintenance: null,

        // Sprint 5: Dashboard, budget, price history
        dashboard: null,
        dashboardLoading: false,

        // Sprint 6: Vehicle photo
        vehiclePhotoUrl: null,

        // Sprint 7: Reminders & Warranties
        reminders: null,
        remindersLoading: false,
        reminderBadge: 0,

        // Sprint 8: Dark mode, VIN decoder
        darkMode: localStorage.getItem('darkMode') === 'true',

        // Fuel
        fuelRecords: [],
        fuelStats: null,
        fuelLoading: false,
        showAddFuelModal: false,
        newFuel: { date: '', mileage: '', liters: '', price_total: '', station_name: '', is_full_tank: true },

        // Tax/Insurance
        taxRecords: [],
        taxLoading: false,
        showAddTaxModal: false,
        newTax: { record_type: 'insurance', name: '', provider: '', date: '', cost: '', next_renewal_date: '', renewal_frequency: 'annual' },

        // Notes
        vehicleNotes: [],
        notesLoading: false,
        newNoteContent: '',
        notesSearch: '',

        // Access/Sharing
        vehicleAccess: [],
        accessLoading: false,
        shareEmail: '',
        shareRole: 'viewer',
        sharedWithMe: [],

        // Double-submit prevention flags
        addingFuel: false,
        addingTax: false,
        addingNote: false,
        sharing: false,
        changingPassword: false,

        // Settings
        settingsView: 'profile',
        changePasswordForm: { current: '', new_password: '', confirm: '' },

        // Chat state
        chatVehicleId: null,
        conversations: [],
        currentConversation: null,
        chatMessages: [],
        chatInput: '',
        chatLoading: false,

        // Mobile menu
        mobileMenuOpen: false,

        // Toast notifications
        toasts: [],
        showToast(message, type = 'info', duration = 4000) {
            const id = Date.now();
            this.toasts.push({ id, message, type });
            setTimeout(() => { this.toasts = this.toasts.filter(t => t.id !== id); }, duration);
        },

        // Confirm modal (replaces native confirm())
        confirmPromise: null,
        confirmMessage: '',
        showConfirm(message) {
            this.confirmMessage = message;
            return new Promise(resolve => { this.confirmPromise = resolve; });
        },
        resolveConfirm(result) {
            if (this.confirmPromise) { this.confirmPromise(result); this.confirmPromise = null; }
            this.confirmMessage = '';
        },

        // i18n helper
        t(key, params) { return I18N.t(key, params); },

        async init() {
            if (this.darkMode) document.documentElement.classList.add('dark');
            await I18N.loadLocale('fr');
            this.t = (key, params) => I18N.t(key, params);
            await this.checkAuth();
        },

        // Cleanup EventSource on component destroy (T-D03)
        destroy() {
            if (this.batchEventSource) {
                this.batchEventSource.close();
                this.batchEventSource = null;
            }
        },

        // --- Auth ---
        async checkAuth() {
            try {
                const res = await safeFetch('/api/auth/me');
                if (res.ok) {
                    this.currentUser = await res.json();
                    this.authenticated = true;
                    await this.loadVehicles();
                }
            } catch (e) {
                console.warn('Auth check failed:', e.message);
            }
        },

        async doLogin() {
            this.authError = '';
            this.authLoading = true;
            try {
                const res = await safeFetch('/api/auth/login', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ email: this.authEmail, password: this.authPassword }),
                });
                if (res.ok) {
                    this.currentUser = await res.json();
                    this.authenticated = true;
                    this.authEmail = '';
                    this.authPassword = '';
                    await this.loadVehicles();
                } else {
                    const data = await res.json();
                    this.authError = data.detail || this.t('auth.login_error');
                }
            } catch (e) {
                this.authError = this.t('auth.network_error');
            }
            this.authLoading = false;
        },

        async doRegister() {
            this.authError = '';
            this.authLoading = true;
            try {
                const res = await safeFetch('/api/auth/register', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ email: this.authEmail, password: this.authPassword }),
                });
                if (res.ok) {
                    this.currentUser = await res.json();
                    this.authenticated = true;
                    this.authEmail = '';
                    this.authPassword = '';
                    await this.loadVehicles();
                } else {
                    const data = await res.json();
                    this.authError = data.detail || this.t('common.error');
                }
            } catch (e) {
                this.authError = this.t('auth.network_error');
            }
            this.authLoading = false;
        },

        async doLogout() {
            try {
                await safeFetch('/api/auth/logout', { method: 'POST' });
            } catch (e) {
                console.warn('Logout request failed:', e.message);
            }
            this.authenticated = false;
            this.currentUser = null;
            this.vehicles = [];
            this.selectedVehicle = null;
        },

        // --- Vehicles ---
        async loadVehicles() {
            try {
                const res = await safeFetch('/api/vehicles');
                if (res.ok) {
                    this.vehicles = await res.json();
                }
            } catch (e) {
                console.error('Erreur chargement vehicules:', e.message);
            }
        },

        async addVehicle() {
            try {
                const res = await safeFetch('/api/vehicles', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ name: this.newVehicle.name }),
                });
                if (res.ok) {
                    this.showAddVehicle = false;
                    this.newVehicle = { name: '' };
                    await this.loadVehicles();
                    this.showToast(this.t('toasts.vehicle_created'), 'success');
                } else {
                    this.showToast(this.t('toasts.vehicle_create_error'), 'error');
                }
            } catch (e) {
                this.showToast(this.t('toasts.network_error', { message: e.message }), 'error');
            }
        },

        openEditVehicle() {
            const v = this.selectedVehicle;
            this.editVehicleData = {
                name: v.name || '', brand: v.brand || '', model: v.model || '',
                year: v.year || '', plate_number: v.plate_number || '',
                vin: v.vin || '', fuel_type: v.fuel_type || '',
                initial_mileage: v.initial_mileage || '', purchase_date: v.purchase_date || '',
            };
            this.showEditVehicle = true;
        },

        async saveVehicle() {
            const data = {};
            for (const [k, v] of Object.entries(this.editVehicleData)) {
                if (v !== '' && v !== null) {
                    data[k] = ['year', 'initial_mileage'].includes(k) ? parseInt(v) || null : v;
                }
            }
            try {
                const res = await safeFetch(`/api/vehicles/${this.selectedVehicle.id}`, {
                    method: 'PATCH',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(data),
                });
                if (res.ok) {
                    this.showEditVehicle = false;
                    await this.loadVehicles();
                    // Update selectedVehicle
                    this.selectedVehicle = this.vehicles.find(v => v.id === this.selectedVehicle.id) || this.selectedVehicle;
                    this.showToast(this.t('toasts.vehicle_saved'), 'success');
                } else {
                    this.showToast(this.t('toasts.vehicle_save_error'), 'error');
                }
            } catch (e) {
                this.showToast(this.t('toasts.network_error', { message: e.message }), 'error');
            }
        },

        async selectVehicle(v) {
            this.selectedVehicle = v;
            this.detailTab = 'analysis';
            this.uploadResult = null;
            this.batchProgress = null;
            this.batchResults = [];
            this.analysis = null;
            this.stats = null;
            this.selectedFiles = [];
            this.loadVehiclePhoto();
            await Promise.all([
                this.loadMaintenance(v.id),
                this.loadCTReports(v.id),
                this.loadDocuments(v.id),
                this.loadPendingDocs(v.id),
                this.loadAnalysis(v.id),
                this.loadStats(v.id),
            ]);
        },

        async loadMaintenance(vehicleId) {
            try {
                const res = await safeFetch(`/api/documents/${vehicleId}/maintenance`);
                if (res.ok) this.maintenanceEvents = await res.json();
            } catch (e) { console.error('Erreur chargement entretiens:', e.message); }
        },

        async loadCTReports(vehicleId) {
            try {
                const res = await safeFetch(`/api/documents/${vehicleId}/ct-reports`);
                if (res.ok) this.ctReports = await res.json();
            } catch (e) { console.error('Erreur chargement CT:', e.message); }
        },

        async loadDocuments(vehicleId) {
            try {
                const res = await safeFetch(`/api/documents/${vehicleId}`);
                if (res.ok) this.documents = await res.json();
            } catch (e) { console.error('Erreur chargement documents:', e.message); }
        },

        async loadPendingDocs(vehicleId) {
            try {
                const res = await safeFetch(`/api/documents/pending/${vehicleId}`);
                if (res.ok) this.pendingDocs = await res.json();
            } catch (e) { console.error('Erreur chargement documents en attente:', e.message); }
        },

        // --- Delete maintenance/CT ---
        async deleteMaintenanceEvent(eventId) {
            const confirmed = await this.showConfirm(this.t('confirm.delete_maintenance'));
            if (!confirmed) return;
            try {
                const res = await safeFetch(`/api/vehicles/${this.selectedVehicle.id}/maintenance/${eventId}`, { method: 'DELETE' });
                if (res.ok) {
                    this.showToast(this.t('toasts.deleted'), 'success');
                    await this._refreshAll();
                }
                else this.showToast(this.t('toasts.delete_error'), 'error');
            } catch (e) { this.showToast(this.t('toasts.network_error', { message: e.message }), 'error'); }
        },

        async deleteCTReport(ctId) {
            const confirmed = await this.showConfirm(this.t('confirm.delete_ct'));
            if (!confirmed) return;
            try {
                const res = await safeFetch(`/api/vehicles/${this.selectedVehicle.id}/ct/${ctId}`, { method: 'DELETE' });
                if (res.ok) {
                    this.showToast(this.t('toasts.deleted'), 'success');
                    await this._refreshAll();
                }
                else this.showToast(this.t('toasts.delete_error'), 'error');
            } catch (e) { this.showToast(this.t('toasts.network_error', { message: e.message }), 'error'); }
        },

        // --- Upload ---
        formatFileSize(bytes) {
            if (bytes < 1024) return bytes + ' o';
            if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' Ko';
            return (bytes / (1024 * 1024)).toFixed(1) + ' Mo';
        },

        async uploadFile(file) {
            if (!this.selectedVehicle) return;
            this.uploading = true;
            this.uploadResult = null;
            this.selectedFiles = [];
            const form = new FormData();
            form.append('vehicle_id', this.selectedVehicle.id);
            form.append('doc_type', this.uploadDocType);
            form.append('file', file);
            try {
                const res = await safeFetch('/api/documents/upload', { method: 'POST', body: form });
                const result = await res.json();
                this.uploadResult = result;
                if (result.needs_clarification) this.openClarifyModal(result);
                await this._refreshAll();
            } catch (e) {
                this.uploadResult = { success: false, message: 'Erreur: ' + e.message };
            }
            this.uploading = false;
        },

        handleFileSelect(event) {
            const files = Array.from(event.target.files);
            if (files.length === 0) return;
            // Show preview
            this.selectedFiles = files.map(f => ({ name: f.name, size: this.formatFileSize(f.size), file: f }));
            // Auto-upload
            if (files.length === 1) this.uploadFile(files[0]);
            else this.batchUpload(files);
            event.target.value = '';
        },

        handleDrop(event) {
            this.dragOver = false;
            const files = Array.from(event.dataTransfer.files);
            if (files.length === 0) return;
            // Show preview
            this.selectedFiles = files.map(f => ({ name: f.name, size: this.formatFileSize(f.size), file: f }));
            if (files.length === 1) this.uploadFile(files[0]);
            else this.batchUpload(files);
        },

        async batchUpload(files) {
            if (!this.selectedVehicle) return;
            this.uploading = true;
            this.uploadResult = null;
            this.batchProgress = { processed: 0, total: files.length, done: false };
            this.batchResults = [];
            // Close any previous EventSource (T-D03)
            if (this.batchEventSource) {
                this.batchEventSource.close();
                this.batchEventSource = null;
            }
            const form = new FormData();
            form.append('vehicle_id', this.selectedVehicle.id);
            form.append('doc_type', this.uploadDocType);
            for (const f of files) form.append('files', f);
            try {
                const res = await safeFetch('/api/documents/batch-upload', { method: 'POST', body: form });
                const data = await res.json();
                const evtSource = new EventSource(`/api/documents/batch-status/${data.batch_id}`);
                this.batchEventSource = evtSource;
                evtSource.onmessage = async (event) => {
                    const msg = JSON.parse(event.data);
                    this.batchProgress = { ...this.batchProgress, ...msg };
                    if (msg.result) this.batchResults.push(msg.result);
                    if (msg.done) {
                        evtSource.close();
                        this.batchEventSource = null;
                        this.uploading = false;
                        this.selectedFiles = [];
                        await this._refreshAll();
                    }
                };
                evtSource.onerror = () => {
                    evtSource.close();
                    this.batchEventSource = null;
                    this.uploading = false;
                    this.batchProgress = { ...this.batchProgress, done: true };
                };
            } catch (e) {
                this.uploading = false;
                this.batchProgress = { processed: 0, total: files.length, done: true, error_count: files.length, success_count: 0 };
            }
        },

        // --- Date clarification ---
        openClarifyModal(result) {
            this.clarifyDoc = { document_id: result.document_id, doc_type: result.doc_type, extracted_date: result.extracted_date, data: result.data };
            this.clarifyDate = result.extracted_date || '';
            this.showClarifyModal = true;
        },

        openClarifyFromPending(pending) {
            this.clarifyDoc = { document_id: pending.id, doc_type: pending.doc_type, extracted_date: pending.extracted_date, filename: pending.original_filename, garage_name: pending.garage_name, mileage: pending.mileage, total_cost: pending.total_cost };
            this.clarifyDate = pending.extracted_date || '';
            this.showClarifyModal = true;
        },

        async confirmDate() {
            if (!this.clarifyDoc || !this.clarifyDate) return;
            try {
                const res = await safeFetch(`/api/documents/${this.clarifyDoc.document_id}/confirm`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ date: this.clarifyDate }) });
                const result = await res.json();
                this.uploadResult = result;
                this.showClarifyModal = false;
                this.clarifyDoc = null;
                await this._refreshAll();
            } catch (e) {
                this.uploadResult = { success: false, message: 'Erreur: ' + e.message };
            }
        },

        async _refreshAll() {
            if (!this.selectedVehicle) return;
            await Promise.all([
                this.loadMaintenance(this.selectedVehicle.id),
                this.loadCTReports(this.selectedVehicle.id),
                this.loadDocuments(this.selectedVehicle.id),
                this.loadPendingDocs(this.selectedVehicle.id),
                this.loadAnalysis(this.selectedVehicle.id),
                this.loadStats(this.selectedVehicle.id),
                this.loadVehicles(),
            ]);
        },

        // --- Analysis ---
        async loadAnalysis(vehicleId) {
            this.analysisLoading = true;
            try {
                const res = await safeFetch(`/api/vehicles/${vehicleId}/analysis`);
                if (res.ok) this.analysis = await res.json();
                else this.analysis = null;
            } catch (e) { this.analysis = null; }
            this.analysisLoading = false;
        },

        async loadStats(vehicleId) {
            this.statsLoading = true;
            try {
                const res = await safeFetch(`/api/vehicles/${vehicleId}/stats`);
                if (res.ok) this.stats = await res.json();
                else this.stats = null;
            } catch (e) { this.stats = null; }
            this.statsLoading = false;
        },

        renderCharts() {
            if (!this.stats) return;
            this.$nextTick(() => {
                this._renderSpendingChart();
                this._renderMileageChart();
                this._renderCategoryChart();
            });
        },

        _renderSpendingChart() {
            const ctx = this.$refs.spendingChart;
            if (!ctx || !this.stats?.spending_by_month?.length) return;
            if (ctx._chart) ctx._chart.destroy();
            const data = this.stats.spending_by_month;
            ctx._chart = new Chart(ctx, {
                type: 'bar',
                data: {
                    labels: data.map(d => d.month),
                    datasets: [{
                        label: 'Depenses (EUR)',
                        data: data.map(d => d.amount),
                        backgroundColor: 'rgba(14, 165, 233, 0.6)',
                        borderColor: 'rgba(14, 165, 233, 1)',
                        borderWidth: 1,
                    }]
                },
                options: { responsive: true, plugins: { legend: { display: false } }, scales: { y: { beginAtZero: true } } }
            });
        },

        _renderMileageChart() {
            const ctx = this.$refs.mileageChart;
            if (!ctx || !this.stats?.mileage_timeline?.length) return;
            if (ctx._chart) ctx._chart.destroy();
            const data = this.stats.mileage_timeline;
            ctx._chart = new Chart(ctx, {
                type: 'line',
                data: {
                    labels: data.map(d => d.date),
                    datasets: [{
                        label: 'Kilometrage',
                        data: data.map(d => d.km),
                        borderColor: 'rgba(34, 197, 94, 1)',
                        backgroundColor: 'rgba(34, 197, 94, 0.1)',
                        fill: true,
                        tension: 0.3,
                    }]
                },
                options: { responsive: true, plugins: { legend: { display: false } } }
            });
        },

        _renderCategoryChart() {
            const ctx = this.$refs.categoryChart;
            if (!ctx || !this.stats?.spending_by_category?.length) return;
            if (ctx._chart) ctx._chart.destroy();
            const data = this.stats.spending_by_category.slice(0, 8);
            const colors = ['#0ea5e9', '#22c55e', '#f59e0b', '#ef4444', '#8b5cf6', '#ec4899', '#14b8a6', '#f97316'];
            ctx._chart = new Chart(ctx, {
                type: 'doughnut',
                data: {
                    labels: data.map(d => d.category),
                    datasets: [{
                        data: data.map(d => d.amount),
                        backgroundColor: colors,
                    }]
                },
                options: { responsive: true, plugins: { legend: { position: 'right' } } }
            });
        },

        async exportPDF() {
            if (!this.selectedVehicle) return;
            try {
                const res = await safeFetch(`/api/vehicles/${this.selectedVehicle.id}/export-pdf`);
                if (res.ok) {
                    const blob = await res.blob();
                    const url = URL.createObjectURL(blob);
                    const a = document.createElement('a');
                    a.href = url;
                    a.download = `rapport_${this.selectedVehicle.name.replace(/\s/g, '_')}.pdf`;
                    a.click();
                    URL.revokeObjectURL(url);
                } else {
                    this.showToast(this.t('toasts.export_pdf_error'), 'error');
                }
            } catch (e) {
                this.showToast(this.t('toasts.network_error', { message: e.message }), 'error');
            }
        },

        // --- Sprint 5: Dashboard ---
        async loadDashboard() {
            this.dashboardLoading = true;
            try {
                const res = await safeFetch('/api/vehicles/dashboard');
                if (res.ok) this.dashboard = await res.json();
            } catch (e) { this.dashboard = null; }
            this.dashboardLoading = false;
        },

        async uploadVehiclePhoto(event) {
            const file = event.target.files[0];
            if (!file || !this.selectedVehicle) return;
            const formData = new FormData();
            formData.append('file', file);
            try {
                const res = await safeFetch(`/api/vehicles/${this.selectedVehicle.id}/photo`, { method: 'POST', body: formData });
                if (res.ok) {
                    this.vehiclePhotoUrl = `/api/vehicles/${this.selectedVehicle.id}/photo?t=${Date.now()}`;
                } else {
                    this.showToast(this.t('toasts.photo_upload_error'), 'error');
                }
            } catch (e) {
                this.showToast(this.t('toasts.network_error', { message: e.message }), 'error');
            }
        },

        loadVehiclePhoto() {
            if (this.selectedVehicle && this.selectedVehicle.photo_path) {
                this.vehiclePhotoUrl = `/api/vehicles/${this.selectedVehicle.id}/photo?t=${Date.now()}`;
            } else {
                this.vehiclePhotoUrl = null;
            }
        },

        // --- Sprint 8: Dark mode & VIN ---
        toggleDarkMode() {
            this.darkMode = !this.darkMode;
            localStorage.setItem('darkMode', this.darkMode);
            document.documentElement.classList.toggle('dark', this.darkMode);
        },

        // --- Sprint 7: Reminders ---
        async loadReminders() {
            if (!this.selectedVehicle) return;
            this.remindersLoading = true;
            try {
                const res = await safeFetch(`/api/vehicles/${this.selectedVehicle.id}/reminders`);
                if (res.ok) {
                    this.reminders = await res.json();
                    this.reminderBadge = this.reminders.counts.critical + this.reminders.counts.high;
                }
            } finally { this.remindersLoading = false; }
        },

        reminderPriorityColor(p) {
            return { critical: 'bg-red-100 text-red-800 border-red-200', high: 'bg-orange-100 text-orange-800 border-orange-200', medium: 'bg-yellow-100 text-yellow-800 border-yellow-200', low: 'bg-gray-100 text-gray-600 border-gray-200' }[p] || 'bg-gray-100';
        },

        reminderPriorityLabel(p) {
            return { critical: 'URGENT', high: 'Important', medium: 'A prevoir', low: 'Info' }[p] || p;
        },

        // --- Sprint 4: Filters & Search ---
        async searchMaintenance() {
            if (!this.selectedVehicle) return;
            const f = this.maintenanceFilter;
            if (!f.q && !f.event_type && !f.date_from && !f.date_to) {
                this.filteredMaintenance = null;
                return;
            }
            const params = new URLSearchParams();
            if (f.q) params.set('q', f.q);
            if (f.event_type) params.set('event_type', f.event_type);
            if (f.date_from) params.set('date_from', f.date_from);
            if (f.date_to) params.set('date_to', f.date_to);
            try {
                const res = await safeFetch(`/api/vehicles/${this.selectedVehicle.id}/maintenance-search?${params}`);
                if (res.ok) { const data = await res.json(); this.filteredMaintenance = data.items || data; }
            } catch (e) { console.error('Erreur recherche:', e.message); }
        },

        clearFilter() {
            this.maintenanceFilter = { q: '', event_type: '', date_from: '', date_to: '' };
            this.filteredMaintenance = null;
        },

        get displayedMaintenance() {
            return this.filteredMaintenance !== null ? this.filteredMaintenance : this.maintenanceEvents;
        },

        async exportCSV() {
            if (!this.selectedVehicle) return;
            try {
                const res = await safeFetch(`/api/vehicles/${this.selectedVehicle.id}/export-csv`);
                if (res.ok) {
                    const blob = await res.blob();
                    const url = URL.createObjectURL(blob);
                    const a = document.createElement('a');
                    a.href = url;
                    a.download = `historique_${this.selectedVehicle.name.replace(/\s/g, '_')}.csv`;
                    a.click();
                    URL.revokeObjectURL(url);
                } else {
                    this.showToast(this.t('toasts.export_csv_error'), 'error');
                }
            } catch (e) {
                this.showToast(this.t('toasts.network_error', { message: e.message }), 'error');
            }
        },

        // --- Chat ---
        async loadConversations() {
            let url = '/api/chat/conversations';
            if (this.chatVehicleId) url += `?vehicle_id=${this.chatVehicleId}`;
            try {
                const res = await safeFetch(url);
                if (res.ok) this.conversations = await res.json();
            } catch (e) { console.error('Erreur chargement conversations:', e.message); }
            // Auto-select vehicle if only one exists
            if (!this.chatVehicleId && this.vehicles.length === 1) {
                this.chatVehicleId = this.vehicles[0].id;
            }
        },

        newConversation() {
            this.currentConversation = null;
            this.chatMessages = [];
            if (!this.chatVehicleId && this.vehicles.length > 0) this.chatVehicleId = this.vehicles[0].id;
        },

        async selectConversation(c) {
            this.currentConversation = c;
            try {
                const res = await safeFetch(`/api/chat/conversations/${c.id}/messages`);
                if (res.ok) this.chatMessages = await res.json();
            } catch (e) { console.error('Erreur chargement messages:', e.message); }
            this.$nextTick(() => this.scrollChat());
        },

        async deleteConversation(c, event) {
            event.stopPropagation();
            const confirmed = await this.showConfirm(this.t('confirm.delete_conversation'));
            if (!confirmed) return;
            try {
                const res = await safeFetch(`/api/chat/conversations/${c.id}`, { method: 'DELETE' });
                if (res.ok) {
                    if (this.currentConversation?.id === c.id) {
                        this.currentConversation = null;
                        this.chatMessages = [];
                    }
                    await this.loadConversations();
                    this.showToast(this.t('toasts.conversation_deleted'), 'success');
                } else {
                    this.showToast(this.t('toasts.delete_error'), 'error');
                }
            } catch (e) {
                this.showToast(this.t('toasts.network_error', { message: e.message }), 'error');
            }
        },

        conversationPreview(c) {
            if (c.last_message) {
                return c.last_message.length > 60 ? c.last_message.substring(0, 60) + '...' : c.last_message;
            }
            return '';
        },

        async sendMessage() {
            const text = this.chatInput.trim();
            if (!text) return;
            if (!this.chatVehicleId && !this.currentConversation) {
                if (this.vehicles.length > 0) this.chatVehicleId = this.vehicles[0].id;
                else { this.showToast(this.t('chat.add_vehicle_first'), 'warning'); return; }
            }
            this.chatInput = '';
            this.chatLoading = true;
            this.chatMessages.push({ id: Date.now(), role: 'user', content: text, created_at: new Date().toISOString() });
            this.$nextTick(() => this.scrollChat());
            try {
                const res = await safeFetch('/api/chat', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ message: text, conversation_id: this.currentConversation?.id || null, vehicle_id: this.chatVehicleId }) });
                const data = await res.json();
                if (!this.currentConversation) {
                    this.currentConversation = { id: data.conversation_id, title: text.substring(0, 80) };
                    await this.loadConversations();
                }
                this.chatMessages.push({ id: Date.now() + 1, role: 'assistant', content: data.message, created_at: new Date().toISOString() });
            } catch (e) {
                this.chatMessages.push({ id: Date.now() + 1, role: 'assistant', content: 'Erreur: ' + e.message, created_at: new Date().toISOString() });
            }
            this.chatLoading = false;
            this.$nextTick(() => this.scrollChat());
        },

        scrollChat() { const el = this.$refs.chatMessages; if (el) el.scrollTop = el.scrollHeight; },

        formatMarkdown(text) {
            if (!text) return '';
            let html = text
                .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
                .replace(/```([\s\S]*?)```/g, '<pre><code>$1</code></pre>')
                .replace(/`([^`]+)`/g, '<code>$1</code>')
                .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
                .replace(/###\s+(.+)$/gm, '<h3 class="font-bold mt-2">$1</h3>')
                .replace(/^\s*[-*]\s+(.+)$/gm, '<li>$1</li>')
                .replace(/(<li>.*<\/li>)/s, '<ul>$1</ul>')
                .replace(/\n/g, '<br>');
            html = '<div class="chat-md">' + html + '</div>';
            // Sanitize HTML output (T-D01 - XSS prevention)
            if (typeof DOMPurify !== 'undefined') {
                return DOMPurify.sanitize(html, {
                    ALLOWED_TAGS: ['div', 'p', 'br', 'strong', 'em', 'code', 'pre', 'ul', 'ol', 'li', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'a', 'blockquote', 'table', 'thead', 'tbody', 'tr', 'th', 'td'],
                    ALLOWED_ATTR: ['class', 'href', 'target', 'rel'],
                });
            }
            return html;
        },

        // --- Fuel ---
        async loadFuel() {
            if (!this.selectedVehicle?.id) return;
            this.fuelLoading = true;
            try {
                const [recRes, statsRes] = await Promise.all([
                    safeFetch(`/api/vehicles/${this.selectedVehicle.id}/fuel`),
                    safeFetch(`/api/vehicles/${this.selectedVehicle.id}/fuel/stats`),
                ]);
                if (!this.selectedVehicle) return;
                if (recRes.status === 404 || statsRes.status === 404) {
                    this.selectedVehicle = null;
                    this.showToast(this.t('toasts.vehicle_not_found'), 'warning');
                    return;
                }
                if (recRes.ok) this.fuelRecords = await recRes.json();
                if (statsRes.ok) this.fuelStats = await statsRes.json();
            } catch (e) {
                console.error('Erreur chargement carburant:', e.message);
            } finally {
                this.fuelLoading = false;
            }
            this.$nextTick(() => this.renderFuelChart());
        },

        async addFuel() {
            if (!this.selectedVehicle || this.addingFuel) return;
            this.addingFuel = true;
            const body = {
                date: this.newFuel.date,
                mileage: parseInt(this.newFuel.mileage) || 0,
                liters: parseFloat(this.newFuel.liters) || 0,
                price_total: parseFloat(this.newFuel.price_total) || 0,
                station_name: this.newFuel.station_name || null,
                is_full_tank: this.newFuel.is_full_tank,
            };
            try {
                const res = await safeFetch(`/api/vehicles/${this.selectedVehicle.id}/fuel`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(body),
                });
                if (res.ok) {
                    this.newFuel = { date: '', mileage: '', liters: '', price_total: '', station_name: '', is_full_tank: true };
                    this.showToast(this.t('toasts.fuel_added'), 'success');
                    this.showAddFuelModal = false;
                    await this.loadFuel();
                } else {
                    const data = await res.json();
                    this.showToast(data.detail || this.t('toasts.fuel_error'), 'error');
                }
            } catch (e) {
                this.showToast(this.t('toasts.network_error', { message: e.message }), 'error');
            } finally {
                this.addingFuel = false;
            }
        },

        async deleteFuel(id) {
            const confirmed = await this.showConfirm(this.t('confirm.delete_fuel'));
            if (!confirmed) return;
            try {
                const res = await safeFetch(`/api/vehicles/${this.selectedVehicle.id}/fuel/${id}`, { method: 'DELETE' });
                if (res.ok) {
                    this.showToast(this.t('toasts.fuel_deleted'), 'success');
                    await this.loadFuel();
                } else {
                    this.showToast(this.t('toasts.delete_error'), 'error');
                }
            } catch (e) {
                this.showToast(this.t('toasts.network_error', { message: e.message }), 'error');
            }
        },

        renderFuelChart() {
            const ctx = this.$refs.fuelChart;
            if (!ctx || !this.fuelStats?.records?.length) return;
            if (ctx._chart) ctx._chart.destroy();
            const records = this.fuelStats.records.filter(r => r.consumption != null);
            if (records.length === 0) return;
            ctx._chart = new Chart(ctx, {
                type: 'line',
                data: {
                    labels: records.map(r => r.date),
                    datasets: [{
                        label: 'L/100km',
                        data: records.map(r => r.consumption),
                        borderColor: '#f59e0b',
                        backgroundColor: 'rgba(245, 158, 11, 0.1)',
                        fill: true,
                        tension: 0.3,
                        pointBackgroundColor: '#f59e0b',
                    }]
                },
                options: {
                    responsive: true,
                    plugins: { legend: { display: false } },
                    scales: { y: { beginAtZero: false, title: { display: true, text: 'L/100km' } } }
                }
            });
        },

        // --- Tax/Insurance ---
        async loadTaxInsurance() {
            if (!this.selectedVehicle?.id) return;
            this.taxLoading = true;
            try {
                const res = await safeFetch(`/api/vehicles/${this.selectedVehicle.id}/tax-insurance`);
                if (!this.selectedVehicle) return;
                if (res.status === 404) {
                    this.selectedVehicle = null;
                    this.showToast(this.t('toasts.vehicle_not_found'), 'warning');
                    return;
                }
                if (res.ok) this.taxRecords = await res.json();
            } catch (e) {
                console.error('Erreur chargement taxes:', e.message);
            } finally {
                this.taxLoading = false;
            }
        },

        async addTaxInsurance() {
            if (!this.selectedVehicle || this.addingTax) return;
            this.addingTax = true;
            const body = {
                record_type: this.newTax.record_type,
                name: this.newTax.name,
                provider: this.newTax.provider || null,
                date: this.newTax.date,
                cost: parseFloat(this.newTax.cost) || 0,
                next_renewal_date: this.newTax.next_renewal_date || null,
                renewal_frequency: this.newTax.renewal_frequency || null,
            };
            try {
                const res = await safeFetch(`/api/vehicles/${this.selectedVehicle.id}/tax-insurance`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(body),
                });
                if (res.ok) {
                    this.newTax = { record_type: 'insurance', name: '', provider: '', date: '', cost: '', next_renewal_date: '', renewal_frequency: 'annual' };
                    this.showToast(this.t('toasts.tax_added'), 'success');
                    this.showAddTaxModal = false;
                    await this.loadTaxInsurance();
                } else {
                    const data = await res.json();
                    this.showToast(data.detail || this.t('toasts.tax_error'), 'error');
                }
            } catch (e) {
                this.showToast(this.t('toasts.network_error', { message: e.message }), 'error');
            } finally {
                this.addingTax = false;
            }
        },

        async deleteTaxInsurance(id) {
            const confirmed = await this.showConfirm(this.t('confirm.delete_tax'));
            if (!confirmed) return;
            try {
                const res = await safeFetch(`/api/vehicles/${this.selectedVehicle.id}/tax-insurance/${id}`, { method: 'DELETE' });
                if (res.ok) {
                    this.showToast(this.t('toasts.tax_deleted'), 'success');
                    await this.loadTaxInsurance();
                } else {
                    this.showToast(this.t('toasts.delete_error'), 'error');
                }
            } catch (e) {
                this.showToast(this.t('toasts.network_error', { message: e.message }), 'error');
            }
        },

        getTaxStatus(record) {
            if (!record.next_renewal_date) return 'unknown';
            const now = new Date();
            const renewal = new Date(record.next_renewal_date);
            const diffDays = (renewal - now) / (1000 * 60 * 60 * 24);
            if (diffDays < 0) return 'expired';
            if (diffDays < 30) return 'expiring';
            return 'valid';
        },

        getTaxStatusLabel(record) {
            const s = this.getTaxStatus(record);
            return { valid: 'Valide', expiring: 'Bientot', expired: 'Expire', unknown: '—' }[s] || '—';
        },

        getTaxStatusClass(record) {
            const s = this.getTaxStatus(record);
            return {
                valid: 'bg-green-100 text-green-700 border-green-200',
                expiring: 'bg-orange-100 text-orange-700 border-orange-200',
                expired: 'bg-red-100 text-red-700 border-red-200',
                unknown: 'bg-gray-100 text-gray-500 border-gray-200',
            }[s] || 'bg-gray-100 text-gray-500';
        },

        // --- Notes ---
        async loadNotes() {
            if (!this.selectedVehicle?.id) return;
            this.notesLoading = true;
            try {
                const params = new URLSearchParams();
                if (this.notesSearch) params.set('q', this.notesSearch);
                const res = await safeFetch(`/api/vehicles/${this.selectedVehicle.id}/notes?${params}`);
                if (!this.selectedVehicle) return;
                if (res.status === 404) {
                    this.selectedVehicle = null;
                    this.showToast(this.t('toasts.vehicle_not_found'), 'warning');
                    return;
                }
                if (res.ok) this.vehicleNotes = await res.json();
            } catch (e) {
                console.error('Erreur chargement notes:', e.message);
            } finally {
                this.notesLoading = false;
            }
        },

        async addNote() {
            if (!this.selectedVehicle || !this.newNoteContent.trim() || this.addingNote) return;
            this.addingNote = true;
            try {
                const res = await safeFetch(`/api/vehicles/${this.selectedVehicle.id}/notes`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ content: this.newNoteContent.trim() }),
                });
                if (res.ok) {
                    this.newNoteContent = '';
                    this.showToast(this.t('toasts.note_added'), 'success');
                    await this.loadNotes();
                } else {
                    this.showToast(this.t('toasts.note_error'), 'error');
                }
            } catch (e) {
                this.showToast(this.t('toasts.network_error', { message: e.message }), 'error');
            } finally {
                this.addingNote = false;
            }
        },

        async toggleNotePin(note) {
            try {
                const res = await safeFetch(`/api/vehicles/${this.selectedVehicle.id}/notes/${note.id}`, {
                    method: 'PATCH',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ pinned: !note.pinned }),
                });
                if (res.ok) await this.loadNotes();
            } catch (e) {
                this.showToast(this.t('toasts.network_error', { message: e.message }), 'error');
            }
        },

        async deleteNote(id) {
            const confirmed = await this.showConfirm(this.t('confirm.delete_note'));
            if (!confirmed) return;
            try {
                const res = await safeFetch(`/api/vehicles/${this.selectedVehicle.id}/notes/${id}`, { method: 'DELETE' });
                if (res.ok) {
                    this.showToast(this.t('toasts.note_deleted'), 'success');
                    await this.loadNotes();
                } else {
                    this.showToast(this.t('toasts.delete_error'), 'error');
                }
            } catch (e) {
                this.showToast(this.t('toasts.network_error', { message: e.message }), 'error');
            }
        },

        // --- Access / Sharing ---
        async loadAccess() {
            if (!this.selectedVehicle?.id) return;
            this.accessLoading = true;
            try {
                const res = await safeFetch(`/api/vehicles/${this.selectedVehicle.id}/access`);
                if (!this.selectedVehicle) return;
                if (res.status === 404) {
                    this.selectedVehicle = null;
                    this.showToast(this.t('toasts.vehicle_not_found'), 'warning');
                    return;
                }
                if (res.ok) this.vehicleAccess = await res.json();
            } catch (e) {
                console.error('Erreur chargement acces:', e.message);
            } finally {
                this.accessLoading = false;
            }
        },

        async shareVehicle() {
            if (!this.selectedVehicle || !this.shareEmail.trim() || this.sharing) return;
            this.sharing = true;
            try {
                const res = await safeFetch(`/api/vehicles/${this.selectedVehicle.id}/share`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ email: this.shareEmail.trim(), role: this.shareRole }),
                });
                if (res.ok) {
                    this.shareEmail = '';
                    this.showToast(this.t('toasts.vehicle_shared'), 'success');
                    await this.loadAccess();
                } else {
                    const data = await res.json();
                    this.showToast(data.detail || this.t('toasts.share_error'), 'error');
                }
            } catch (e) {
                this.showToast(this.t('toasts.network_error', { message: e.message }), 'error');
            } finally {
                this.sharing = false;
            }
        },

        async revokeAccess(accessId) {
            const confirmed = await this.showConfirm(this.t('confirm.revoke_access'));
            if (!confirmed) return;
            try {
                const res = await safeFetch(`/api/vehicles/${this.selectedVehicle.id}/access/${accessId}`, { method: 'DELETE' });
                if (res.ok) {
                    this.showToast(this.t('toasts.access_revoked'), 'success');
                    await this.loadAccess();
                } else {
                    this.showToast(this.t('toasts.delete_error'), 'error');
                }
            } catch (e) {
                this.showToast(this.t('toasts.network_error', { message: e.message }), 'error');
            }
        },

        async loadSharedWithMe() {
            try {
                const res = await safeFetch('/api/vehicles/shared-with-me');
                if (res.ok) this.sharedWithMe = await res.json();
            } catch (e) {
                console.error('Erreur chargement partages:', e.message);
            }
        },

        getCurrentUserRole() {
            if (!this.selectedVehicle || !this.currentUser) return 'viewer';
            if (this.selectedVehicle.owner_id === this.currentUser.id) return 'owner';
            const access = this.vehicleAccess.find(a => a.user_id === this.currentUser.id);
            return access?.role || 'viewer';
        },

        // --- Settings ---
        async changePassword() {
            if (this.changePasswordForm.new_password !== this.changePasswordForm.confirm) {
                this.showToast(this.t('toasts.password_mismatch'), 'error');
                return;
            }
            if (this.changingPassword) return;
            this.changingPassword = true;
            try {
                const res = await safeFetch('/api/auth/change-password', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        current_password: this.changePasswordForm.current,
                        new_password: this.changePasswordForm.new_password,
                    }),
                });
                if (res.ok) {
                    this.changePasswordForm = { current: '', new_password: '', confirm: '' };
                    this.showToast(this.t('toasts.password_changed'), 'success');
                } else {
                    const data = await res.json();
                    this.showToast(data.detail || this.t('toasts.password_error'), 'error');
                }
            } catch (e) {
                this.showToast(this.t('toasts.network_error', { message: e.message }), 'error');
            } finally {
                this.changingPassword = false;
            }
        },

        async changeLocale(locale) {
            await I18N.loadLocale(locale);
            this.t = (key, params) => I18N.t(key, params);
            localStorage.setItem('locale', locale);
            this.showToast(this.t('toasts.language_changed'), 'success');
        },
    };
}
