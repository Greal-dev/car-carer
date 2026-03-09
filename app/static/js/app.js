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

        // Chat state
        chatVehicleId: null,
        conversations: [],
        currentConversation: null,
        chatMessages: [],
        chatInput: '',
        chatLoading: false,

        async init() {
            if (this.darkMode) document.documentElement.classList.add('dark');
            await this.checkAuth();
        },

        // --- Auth ---
        async checkAuth() {
            try {
                const res = await fetch('/api/auth/me');
                if (res.ok) {
                    this.currentUser = await res.json();
                    this.authenticated = true;
                    await this.loadVehicles();
                }
            } catch (e) {}
        },

        async doLogin() {
            this.authError = '';
            this.authLoading = true;
            try {
                const res = await fetch('/api/auth/login', {
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
                    this.authError = data.detail || 'Erreur de connexion';
                }
            } catch (e) {
                this.authError = 'Erreur reseau';
            }
            this.authLoading = false;
        },

        async doRegister() {
            this.authError = '';
            this.authLoading = true;
            try {
                const res = await fetch('/api/auth/register', {
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
                    this.authError = data.detail || 'Erreur';
                }
            } catch (e) {
                this.authError = 'Erreur reseau';
            }
            this.authLoading = false;
        },

        async doLogout() {
            await fetch('/api/auth/logout', { method: 'POST' });
            this.authenticated = false;
            this.currentUser = null;
            this.vehicles = [];
            this.selectedVehicle = null;
        },

        // --- Vehicles ---
        async loadVehicles() {
            const res = await fetch('/api/vehicles');
            if (res.ok) {
                this.vehicles = await res.json();
            }
        },

        async addVehicle() {
            const res = await fetch('/api/vehicles', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ name: this.newVehicle.name }),
            });
            if (res.ok) {
                this.showAddVehicle = false;
                this.newVehicle = { name: '' };
                await this.loadVehicles();
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
            const res = await fetch(`/api/vehicles/${this.selectedVehicle.id}`, {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(data),
            });
            if (res.ok) {
                this.showEditVehicle = false;
                await this.loadVehicles();
                // Update selectedVehicle
                this.selectedVehicle = this.vehicles.find(v => v.id === this.selectedVehicle.id) || this.selectedVehicle;
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
            const res = await fetch(`/api/documents/${vehicleId}/maintenance`);
            if (res.ok) this.maintenanceEvents = await res.json();
        },

        async loadCTReports(vehicleId) {
            const res = await fetch(`/api/documents/${vehicleId}/ct-reports`);
            if (res.ok) this.ctReports = await res.json();
        },

        async loadDocuments(vehicleId) {
            const res = await fetch(`/api/documents/${vehicleId}`);
            if (res.ok) this.documents = await res.json();
        },

        async loadPendingDocs(vehicleId) {
            const res = await fetch(`/api/documents/pending/${vehicleId}`);
            if (res.ok) this.pendingDocs = await res.json();
        },

        // --- Delete maintenance/CT ---
        async deleteMaintenanceEvent(eventId) {
            if (!confirm('Supprimer cet entretien ?')) return;
            const res = await fetch(`/api/vehicles/${this.selectedVehicle.id}/maintenance/${eventId}`, { method: 'DELETE' });
            if (res.ok) await this._refreshAll();
        },

        async deleteCTReport(ctId) {
            if (!confirm('Supprimer ce controle technique ?')) return;
            const res = await fetch(`/api/vehicles/${this.selectedVehicle.id}/ct/${ctId}`, { method: 'DELETE' });
            if (res.ok) await this._refreshAll();
        },

        // --- Upload ---
        async uploadFile(file) {
            if (!this.selectedVehicle) return;
            this.uploading = true;
            this.uploadResult = null;
            const form = new FormData();
            form.append('vehicle_id', this.selectedVehicle.id);
            form.append('doc_type', this.uploadDocType);
            form.append('file', file);
            try {
                const res = await fetch('/api/documents/upload', { method: 'POST', body: form });
                const result = await res.json();
                this.uploadResult = result;
                if (result.needs_clarification) this.openClarifyModal(result);
                await this._refreshAll();
            } catch (e) {
                this.uploadResult = { success: false, message: 'Erreur reseau: ' + e.message };
            }
            this.uploading = false;
        },

        handleFileSelect(event) {
            const files = Array.from(event.target.files);
            if (files.length === 0) return;
            if (files.length === 1) this.uploadFile(files[0]);
            else this.batchUpload(files);
            event.target.value = '';
        },

        handleDrop(event) {
            this.dragOver = false;
            const files = Array.from(event.dataTransfer.files);
            if (files.length === 0) return;
            if (files.length === 1) this.uploadFile(files[0]);
            else this.batchUpload(files);
        },

        async batchUpload(files) {
            if (!this.selectedVehicle) return;
            this.uploading = true;
            this.uploadResult = null;
            this.batchProgress = { processed: 0, total: files.length, done: false };
            this.batchResults = [];
            const form = new FormData();
            form.append('vehicle_id', this.selectedVehicle.id);
            form.append('doc_type', this.uploadDocType);
            for (const f of files) form.append('files', f);
            try {
                const res = await fetch('/api/documents/batch-upload', { method: 'POST', body: form });
                const data = await res.json();
                const evtSource = new EventSource(`/api/documents/batch-status/${data.batch_id}`);
                evtSource.onmessage = async (event) => {
                    const msg = JSON.parse(event.data);
                    this.batchProgress = { ...this.batchProgress, ...msg };
                    if (msg.result) this.batchResults.push(msg.result);
                    if (msg.done) { evtSource.close(); this.uploading = false; await this._refreshAll(); }
                };
                evtSource.onerror = () => { evtSource.close(); this.uploading = false; this.batchProgress = { ...this.batchProgress, done: true }; };
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
                const res = await fetch(`/api/documents/${this.clarifyDoc.document_id}/confirm`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ date: this.clarifyDate }) });
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
                const res = await fetch(`/api/vehicles/${vehicleId}/analysis`);
                if (res.ok) this.analysis = await res.json();
                else this.analysis = null;
            } catch (e) { this.analysis = null; }
            this.analysisLoading = false;
        },

        async loadStats(vehicleId) {
            this.statsLoading = true;
            try {
                const res = await fetch(`/api/vehicles/${vehicleId}/stats`);
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
            const res = await fetch(`/api/vehicles/${this.selectedVehicle.id}/export-pdf`);
            if (res.ok) {
                const blob = await res.blob();
                const url = URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = `rapport_${this.selectedVehicle.name.replace(/\s/g, '_')}.pdf`;
                a.click();
                URL.revokeObjectURL(url);
            }
        },

        // --- Sprint 5: Dashboard ---
        async loadDashboard() {
            this.dashboardLoading = true;
            try {
                const res = await fetch('/api/vehicles/dashboard');
                if (res.ok) this.dashboard = await res.json();
            } catch (e) { this.dashboard = null; }
            this.dashboardLoading = false;
        },

        async uploadVehiclePhoto(event) {
            const file = event.target.files[0];
            if (!file || !this.selectedVehicle) return;
            const formData = new FormData();
            formData.append('file', file);
            const res = await fetch(`/api/vehicles/${this.selectedVehicle.id}/photo`, { method: 'POST', body: formData });
            if (res.ok) {
                const data = await res.json();
                this.vehiclePhotoUrl = `/api/vehicles/${this.selectedVehicle.id}/photo?t=${Date.now()}`;
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
                const res = await fetch(`/api/vehicles/${this.selectedVehicle.id}/reminders`);
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
            const res = await fetch(`/api/vehicles/${this.selectedVehicle.id}/maintenance-search?${params}`);
            if (res.ok) { const data = await res.json(); this.filteredMaintenance = data.items || data; }
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
            const res = await fetch(`/api/vehicles/${this.selectedVehicle.id}/export-csv`);
            if (res.ok) {
                const blob = await res.blob();
                const url = URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = `historique_${this.selectedVehicle.name.replace(/\s/g, '_')}.csv`;
                a.click();
                URL.revokeObjectURL(url);
            }
        },

        // --- Chat ---
        async loadConversations() {
            let url = '/api/chat/conversations';
            if (this.chatVehicleId) url += `?vehicle_id=${this.chatVehicleId}`;
            const res = await fetch(url);
            if (res.ok) this.conversations = await res.json();
        },

        newConversation() {
            this.currentConversation = null;
            this.chatMessages = [];
            if (!this.chatVehicleId && this.vehicles.length > 0) this.chatVehicleId = this.vehicles[0].id;
        },

        async selectConversation(c) {
            this.currentConversation = c;
            const res = await fetch(`/api/chat/conversations/${c.id}/messages`);
            if (res.ok) this.chatMessages = await res.json();
            this.$nextTick(() => this.scrollChat());
        },

        async sendMessage() {
            const text = this.chatInput.trim();
            if (!text) return;
            if (!this.chatVehicleId && !this.currentConversation) {
                if (this.vehicles.length > 0) this.chatVehicleId = this.vehicles[0].id;
                else { alert('Ajoutez d\'abord un vehicule.'); return; }
            }
            this.chatInput = '';
            this.chatLoading = true;
            this.chatMessages.push({ id: Date.now(), role: 'user', content: text, created_at: new Date().toISOString() });
            this.$nextTick(() => this.scrollChat());
            try {
                const res = await fetch('/api/chat', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ message: text, conversation_id: this.currentConversation?.id || null, vehicle_id: this.chatVehicleId }) });
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
            return '<div class="chat-md">' + html + '</div>';
        },
    };
}
