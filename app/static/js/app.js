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
            this.detailTab = 'maintenance';
            this.uploadResult = null;
            this.batchProgress = null;
            this.batchResults = [];
            await Promise.all([
                this.loadMaintenance(v.id),
                this.loadCTReports(v.id),
                this.loadDocuments(v.id),
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
                this.uploadResult = await res.json();
                // Refresh data
                await Promise.all([
                    this.loadMaintenance(this.selectedVehicle.id),
                    this.loadCTReports(this.selectedVehicle.id),
                    this.loadDocuments(this.selectedVehicle.id),
                    this.loadVehicles(),
                ]);
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
                        // Refresh all data
                        await Promise.all([
                            this.loadMaintenance(this.selectedVehicle.id),
                            this.loadCTReports(this.selectedVehicle.id),
                            this.loadDocuments(this.selectedVehicle.id),
                            this.loadVehicles(),
                        ]);
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
