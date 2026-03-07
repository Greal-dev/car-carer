function app() {
    return {
        // State
        view: 'vehicles',
        vehicles: [],
        selectedVehicle: null,
        showAddVehicle: false,
        newVehicle: { name: '' },
        detailTab: 'maintenance',
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
        // Alert chat state
        alertChat: null,        // current alert being discussed
        alertMessages: [],
        alertChatInput: '',
        alertChatLoading: false,

        // Chat state
        chatVehicleId: null,
        conversations: [],
        currentConversation: null,
        chatMessages: [],
        chatInput: '',
        chatLoading: false,

        async init() {
            await this.loadVehicles();
        },

        // --- Vehicles ---
        async loadVehicles() {
            const res = await fetch('/api/vehicles');
            this.vehicles = await res.json();
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

        async selectVehicle(v) {
            this.selectedVehicle = v;
            this.detailTab = 'analysis';
            this.uploadResult = null;
            this.batchProgress = null;
            this.batchResults = [];
            this.analysis = null;
            await Promise.all([
                this.loadMaintenance(v.id),
                this.loadCTReports(v.id),
                this.loadDocuments(v.id),
                this.loadPendingDocs(v.id),
                this.loadAnalysis(v.id),
            ]);
        },

        async loadMaintenance(vehicleId) {
            const res = await fetch(`/api/documents/${vehicleId}/maintenance`);
            this.maintenanceEvents = await res.json();
        },

        async loadCTReports(vehicleId) {
            const res = await fetch(`/api/documents/${vehicleId}/ct-reports`);
            this.ctReports = await res.json();
        },

        async loadDocuments(vehicleId) {
            const res = await fetch(`/api/documents/${vehicleId}`);
            this.documents = await res.json();
        },

        async loadPendingDocs(vehicleId) {
            const res = await fetch(`/api/documents/pending/${vehicleId}`);
            this.pendingDocs = await res.json();
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

                if (result.needs_clarification) {
                    this.openClarifyModal(result);
                }

                // Refresh data
                await this._refreshAll();
            } catch (e) {
                this.uploadResult = { success: false, message: 'Erreur reseau: ' + e.message };
            }
            this.uploading = false;
        },

        handleFileSelect(event) {
            const files = Array.from(event.target.files);
            if (files.length === 0) return;
            if (files.length === 1) {
                this.uploadFile(files[0]);
            } else {
                this.batchUpload(files);
            }
            event.target.value = '';
        },

        handleDrop(event) {
            this.dragOver = false;
            const files = Array.from(event.dataTransfer.files);
            if (files.length === 0) return;
            if (files.length === 1) {
                this.uploadFile(files[0]);
            } else {
                this.batchUpload(files);
            }
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
            for (const f of files) {
                form.append('files', f);
            }

            try {
                const res = await fetch('/api/documents/batch-upload', { method: 'POST', body: form });
                const data = await res.json();

                // Listen to SSE for progress
                const evtSource = new EventSource(`/api/documents/batch-status/${data.batch_id}`);
                evtSource.onmessage = async (event) => {
                    const msg = JSON.parse(event.data);
                    this.batchProgress = { ...this.batchProgress, ...msg };
                    if (msg.result) {
                        this.batchResults.push(msg.result);
                    }
                    if (msg.done) {
                        evtSource.close();
                        this.uploading = false;
                        await this._refreshAll();
                    }
                };
                evtSource.onerror = () => {
                    evtSource.close();
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
            this.clarifyDoc = {
                document_id: result.document_id,
                doc_type: result.doc_type,
                extracted_date: result.extracted_date,
                data: result.data,
            };
            this.clarifyDate = result.extracted_date || '';
            this.showClarifyModal = true;
        },

        openClarifyFromPending(pending) {
            this.clarifyDoc = {
                document_id: pending.id,
                doc_type: pending.doc_type,
                extracted_date: pending.extracted_date,
                filename: pending.original_filename,
                garage_name: pending.garage_name,
                mileage: pending.mileage,
                total_cost: pending.total_cost,
            };
            this.clarifyDate = pending.extracted_date || '';
            this.showClarifyModal = true;
        },

        async confirmDate() {
            if (!this.clarifyDoc || !this.clarifyDate) return;

            try {
                const res = await fetch(`/api/documents/${this.clarifyDoc.document_id}/confirm`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ date: this.clarifyDate }),
                });
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
                this.loadVehicles(),
            ]);
        },

        async loadAnalysis(vehicleId) {
            this.analysisLoading = true;
            try {
                const res = await fetch(`/api/vehicles/${vehicleId}/analysis`);
                this.analysis = await res.json();
            } catch (e) {
                this.analysis = null;
            }
            this.analysisLoading = false;
        },

        analysisAlertIcon(level) {
            if (level === 'critical') return { color: 'text-red-600 bg-red-50 border-red-200', badge: 'bg-red-100 text-red-700' };
            if (level === 'warning') return { color: 'text-orange-600 bg-orange-50 border-orange-200', badge: 'bg-orange-100 text-orange-700' };
            if (level === 'ok') return { color: 'text-green-600 bg-green-50 border-green-200', badge: 'bg-green-100 text-green-700' };
            return { color: 'text-blue-600 bg-blue-50 border-blue-200', badge: 'bg-blue-100 text-blue-700' };
        },

        analysisLevelLabel(level) {
            return { critical: 'CRITIQUE', warning: 'ATTENTION', info: 'INFO', ok: 'OK' }[level] || level;
        },

        openAlertChat(alert) {
            this.alertChat = alert;
            this.alertMessages = [];
            this.alertChatInput = '';
            this.alertChatLoading = false;
            // Auto-send initial question
            this._sendAlertMessage("Explique-moi ce probleme, ses causes possibles, son impact, et ce que je dois faire.");
        },

        closeAlertChat() {
            this.alertChat = null;
            this.alertMessages = [];
        },

        async sendAlertMessage() {
            const text = this.alertChatInput.trim();
            if (!text) return;
            this.alertChatInput = '';
            await this._sendAlertMessage(text);
        },

        async _sendAlertMessage(text) {
            this.alertMessages.push({ role: 'user', content: text });
            this.alertChatLoading = true;
            this.$nextTick(() => {
                const el = this.$refs.alertChatMessages;
                if (el) el.scrollTop = el.scrollHeight;
            });

            try {
                const res = await fetch('/api/chat/alert', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        vehicle_id: this.selectedVehicle.id,
                        alert: this.alertChat,
                        messages: this.alertMessages,
                    }),
                });
                const data = await res.json();
                this.alertMessages.push({ role: 'assistant', content: data.message });
            } catch (e) {
                this.alertMessages.push({ role: 'assistant', content: 'Erreur de connexion: ' + e.message });
            }
            this.alertChatLoading = false;
            this.$nextTick(() => {
                const el = this.$refs.alertChatMessages;
                if (el) el.scrollTop = el.scrollHeight;
            });
        },

        // --- Chat ---
        async loadConversations() {
            let url = '/api/chat/conversations';
            if (this.chatVehicleId) url += `?vehicle_id=${this.chatVehicleId}`;
            const res = await fetch(url);
            this.conversations = await res.json();
        },

        newConversation() {
            this.currentConversation = null;
            this.chatMessages = [];
            if (!this.chatVehicleId && this.vehicles.length > 0) {
                this.chatVehicleId = this.vehicles[0].id;
            }
        },

        async selectConversation(c) {
            this.currentConversation = c;
            const res = await fetch(`/api/chat/conversations/${c.id}/messages`);
            this.chatMessages = await res.json();
            this.$nextTick(() => this.scrollChat());
        },

        async sendMessage() {
            const text = this.chatInput.trim();
            if (!text) return;
            if (!this.chatVehicleId && !this.currentConversation) {
                if (this.vehicles.length > 0) {
                    this.chatVehicleId = this.vehicles[0].id;
                } else {
                    alert('Ajoutez d\'abord un vehicule avant de demarrer une conversation.');
                    return;
                }
            }

            this.chatInput = '';
            this.chatLoading = true;

            // Optimistic user message
            const tempMsg = { id: Date.now(), role: 'user', content: text, created_at: new Date().toISOString() };
            this.chatMessages.push(tempMsg);
            this.$nextTick(() => this.scrollChat());

            try {
                const res = await fetch('/api/chat', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        message: text,
                        conversation_id: this.currentConversation?.id || null,
                        vehicle_id: this.chatVehicleId,
                    }),
                });
                const data = await res.json();

                // If new conversation, set it
                if (!this.currentConversation) {
                    this.currentConversation = { id: data.conversation_id, title: text.substring(0, 80) };
                    await this.loadConversations();
                }

                // Add assistant message
                this.chatMessages.push({
                    id: Date.now() + 1,
                    role: 'assistant',
                    content: data.message,
                    created_at: new Date().toISOString(),
                });
            } catch (e) {
                this.chatMessages.push({
                    id: Date.now() + 1,
                    role: 'assistant',
                    content: 'Erreur de connexion: ' + e.message,
                    created_at: new Date().toISOString(),
                });
            }

            this.chatLoading = false;
            this.$nextTick(() => this.scrollChat());
        },

        scrollChat() {
            const el = this.$refs.chatMessages;
            if (el) el.scrollTop = el.scrollHeight;
        },

        formatMarkdown(text) {
            if (!text) return '';
            // Basic markdown: bold, code blocks, inline code, lists
            let html = text
                .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
                .replace(/```([\s\S]*?)```/g, '<pre><code>$1</code></pre>')
                .replace(/`([^`]+)`/g, '<code>$1</code>')
                .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
                .replace(/^\s*[-*]\s+(.+)$/gm, '<li>$1</li>')
                .replace(/(<li>.*<\/li>)/s, '<ul>$1</ul>')
                .replace(/\n/g, '<br>');
            return '<div class="chat-md">' + html + '</div>';
        },
    };
}
