<template>
  <div id="mujoco-container"></div>
  <div class="global-alerts">
    <v-alert
      v-if="isSmallScreen"
      v-model="showSmallScreenAlert"
      type="warning"
      variant="flat"
      density="compact"
      closable
      class="small-screen-alert"
    >
      Screen too small. The control panel is unavailable on small screens. Please use a desktop device.
    </v-alert>
    <v-alert
      v-if="isSafari"
      v-model="showSafariAlert"
      type="warning"
      variant="flat"
      density="compact"
      closable
      class="safari-alert"
    >
      Safari has lower memory limits, which can cause WASM to crash.
    </v-alert>
  </div>
  <div v-if="!isSmallScreen" class="controls">
    <v-card class="controls-card">
      <v-card-title>General Tracking Demo</v-card-title>
      <v-card-text class="py-0 controls-body">
          <v-btn
            href="https://github.com/Axellwppr/humanoid-policy-viewer"
            target="_blank"
            variant="text"
            size="small"
            color="primary"
            class="text-capitalize"
          >
            <v-icon icon="mdi-github" class="mr-1"></v-icon>
            Demo Code
          </v-btn>
          <v-btn
            href="https://github.com/Axellwppr/motion_tracking"
            target="_blank"
            variant="text"
            size="small"
            color="primary"
            class="text-capitalize"
          >
            <v-icon icon="mdi-github" class="mr-1"></v-icon>
            Training Code
          </v-btn>
        <v-divider class="my-2"/>

        <!-- T2M generate -->
        <div class="d-flex align-center mb-1">
          <span class="status-name flex-grow-1">Generate</span>
          <v-icon size="14" :color="bridgeConnected ? 'success' : 'grey'" class="mr-1">mdi-circle</v-icon>
          <span class="text-caption" :class="bridgeConnected ? 'text-success' : 'text-disabled'">
            {{ bridgeConnected ? 'online' : 'offline' }}
          </span>
        </div>
        <v-text-field
          v-model="t2mText"
          density="compact"
          hide-details
          placeholder="e.g. jump jacks"
          :disabled="t2mGenerating || !bridgeConnected || state !== 1"
          @keydown.enter.exact.prevent="onGenerate"
        ></v-text-field>
        <div class="d-flex align-center gap-1 mt-1">
          <v-btn
            color="primary" size="small" variant="flat"
            :loading="t2mGenerating"
            :disabled="!t2mText.trim() || !bridgeConnected || state !== 1"
            @click="onGenerate"
            class="flex-grow-1"
          >Generate</v-btn>
          <span class="text-caption text-medium-emphasis" style="flex-shrink:0">dur</span>
          <input
            v-model.number="t2mLength"
            type="number" min="1" max="20" step="0.5"
            :disabled="t2mGenerating || state !== 1"
            style="width:46px; text-align:center; background:#f5f5f5; border:1px solid #ddd; border-radius:4px; font-size:12px; padding:3px 4px; outline:none; color:#555"
          />
          <span class="text-caption text-medium-emphasis" style="flex-shrink:0">s</span>
        </div>
        <div class="d-flex align-center gap-1 mt-1">
          <span class="text-caption text-medium-emphasis" style="flex-shrink:0">Remote port</span>
          <input
            v-model.number="remotePort"
            type="number" min="1" max="65535" step="1"
            :disabled="!bridgeConnected"
            style="width:64px; text-align:center; background:#f5f5f5; border:1px solid #ddd; border-radius:4px; font-size:12px; padding:3px 4px; outline:none; color:#555"
          />
          <v-btn
            size="small" variant="tonal" color="primary"
            :disabled="!bridgeConnected || isApplyingConfig"
            :loading="isApplyingConfig"
            @click="applyRemotePort"
          >Apply</v-btn>
        </div>
        <div v-if="configMessage" class="text-caption mt-1" :class="configMessageColor">{{ configMessage }}</div>
        <div class="d-flex align-center mt-1">
          <v-checkbox
            v-model="autoReturnDefault"
            label="Auto return to default"
            density="compact" hide-details
          ></v-checkbox>
        </div>
        <div v-if="t2mStatus" class="text-caption mt-1" :class="t2mStatusColor">{{ t2mStatus }}</div>

        <!-- Save -->
        <div v-if="lastSource" class="d-flex align-center gap-1 mt-2">
          <v-text-field
            v-model="saveMotionName"
            density="compact" hide-details
            placeholder="filename (no .npz)"
            :disabled="isSaving"
            class="flex-grow-1"
          ></v-text-field>
          <v-btn
            color="success" size="small" icon variant="flat"
            :disabled="!saveMotionName.trim() || isSaving"
            :loading="isSaving"
            @click="onSave"
            title="Save to data/saved/"
          ><v-icon>mdi-content-save</v-icon></v-btn>
        </div>

        <!-- overwrite confirm -->
        <v-dialog v-model="showOverwriteDialog" max-width="280">
          <v-card>
            <v-card-text class="pt-4">
              <strong>{{ saveMotionName }}.npz</strong> already exists. Overwrite?
            </v-card-text>
            <v-card-actions>
              <v-spacer/>
              <v-btn size="small" variant="text" @click="showOverwriteDialog = false">Cancel</v-btn>
              <v-btn size="small" color="error" variant="flat" @click="onConfirmOverwrite">Overwrite</v-btn>
            </v-card-actions>
          </v-card>
        </v-dialog>

        <!-- Load -->
        <div class="d-flex align-center mt-2 mb-1">
          <span class="status-name flex-grow-1">Load</span>
          <v-btn icon size="x-small" variant="text" @click="refreshFileList" :disabled="!bridgeConnected">
            <v-icon size="16">mdi-refresh</v-icon>
          </v-btn>
        </div>
        <div class="d-flex align-center gap-1">
          <v-select
            v-model="selectedFile"
            :items="fileListItems"
            item-title="name" item-value="name"
            density="compact" hide-details
            placeholder="Select file"
            :disabled="!bridgeConnected || fileList.length === 0 || state !== 1"
            no-data-text="No files (click refresh)"
            @update:modelValue="onFileSelect"
            class="flex-grow-1"
          >
            <template #item="{ item, props }">
              <v-list-item v-bind="props" density="compact">
                <template #append>
                  <v-chip size="x-small" :color="folderChipColor(item.raw.folder)" variant="tonal">
                    {{ folderChipLabel(item.raw.folder) }}
                  </v-chip>
                </template>
              </v-list-item>
            </template>
          </v-select>
          <v-btn color="secondary" size="small" icon variant="flat"
            :disabled="!selectedFile || !bridgeConnected || state !== 1"
            @click="onLoadFile" title="Load"
          ><v-icon>mdi-folder-open</v-icon></v-btn>
          <v-btn color="error" size="small" icon variant="outlined"
            :disabled="!bridgeConnected"
            @click="showClearDialog = true" title="Clear data/generated/"
          ><v-icon>mdi-delete-sweep</v-icon></v-btn>
        </div>

        <!-- clear confirm -->
        <v-dialog v-model="showClearDialog" max-width="280">
          <v-card>
            <v-card-text class="pt-4">Delete all <code>gen_*.npz</code> in data/generated/? data/saved/ and data/dataset/ are not affected.</v-card-text>
            <v-card-actions>
              <v-spacer/>
              <v-btn size="small" variant="text" @click="showClearDialog = false">Cancel</v-btn>
              <v-btn size="small" color="error" variant="flat" @click="onClearGenerated">Clear</v-btn>
            </v-card-actions>
          </v-card>
        </v-dialog>

        <v-divider class="my-2"/>
        <span class="status-name">Policy</span>
        <div v-if="policyDescription" class="text-caption">{{ policyDescription }}</div>
        <v-select
          v-model="currentPolicy"
          :items="policyItems"
          class="mt-2"
          label="Select policy"
          density="compact"
          hide-details
          item-title="title"
          item-value="value"
          :disabled="isPolicyLoading || state !== 1"
          @update:modelValue="onPolicyChange"
        ></v-select>
        <v-progress-linear
          v-if="isPolicyLoading"
          indeterminate
          height="4"
          color="primary"
          class="mt-2"
        ></v-progress-linear>
        <v-alert
          v-if="policyLoadError"
          type="error"
          variant="tonal"
          density="compact"
          class="mt-2"
        >
          {{ policyLoadError }}
        </v-alert>

        <div class="status-legend follow-controls mt-2">
          <span class="status-name">Compliance</span>
          <v-btn
            size="x-small"
            variant="tonal"
            color="primary"
            :disabled="state !== 1"
            @click="toggleCompliance"
          >
            {{ complianceEnabled ? 'On' : 'Off' }}
          </v-btn>
          <span class="status-name">threshold</span>
          <span class="text-caption">{{ complianceThresholdLabel }}</span>
        </div>
        <v-slider
          v-model="complianceThreshold"
          min="10"
          max="20"
          step="0.1"
          density="compact"
          hide-details
          :disabled="state !== 1 || !complianceEnabled"
          @update:modelValue="onComplianceThresholdChange"
        ></v-slider>

        <v-divider class="my-2"/>
        <div class="motion-status" v-if="trackingState">
          <div class="status-legend" v-if="trackingState.available">
            <span class="status-name">Current motion: {{ trackingState.currentName }}</span>
          </div>
        </div>

          <v-progress-linear
            v-if="shouldShowProgress"
            :model-value="progressValue"
            height="5"
            color="primary"
            rounded
            class="mt-3 motion-progress-no-animation"
          ></v-progress-linear>
        <v-alert
          v-if="showBackToDefault"
          type="info"
          variant="tonal"
          density="compact"
          class="mt-3"
        >
          Motion "{{ trackingState.currentName }}" finished. Return to the default pose before starting another clip.
          <v-btn color="primary" block density="compact" @click="backToDefault">
            Back to default pose
          </v-btn>
        </v-alert>

        <v-alert
          v-else-if="showMotionLockedNotice"
          type="warning"
          variant="tonal"
          density="compact"
          class="mt-3"
        >
          "{{ trackingState.currentName }}" is still playing. Wait until it finishes and returns to default pose before switching.
        </v-alert>

        <div v-if="showMotionSelect" class="motion-groups">
          <div v-for="group in motionGroups" :key="group.title" class="motion-group">
            <span class="status-name motion-group-title">{{ group.title }}</span>
            <v-chip
              v-for="item in group.items"
              :key="item.value"
              :disabled="item.disabled"
              :color="currentMotion === item.value ? 'primary' : undefined"
              :variant="currentMotion === item.value ? 'flat' : 'tonal'"
              class="motion-chip"
              size="x-small"
              @click="onMotionChange(item.value)"
            >
              {{ item.title }}
            </v-chip>
          </div>
        </div>

        <v-alert
          v-else-if="!trackingState.available"
          type="info"
          variant="tonal"
          density="compact"
        >
          Loading motion presets…
        </v-alert>

        <v-divider class="my-2"/>
        <div class="upload-section">
          <v-btn
            v-if="!showUploadOptions"
            variant="text"
            density="compact"
            color="primary"
            class="upload-toggle"
            @click="showUploadOptions = true"
          >
            Want to use customized motions?
          </v-btn>
          <template v-else>
            <span class="status-name">Custom motions</span>
            <v-file-input
              v-model="motionUploadFiles"
              label="Upload motion JSON"
              density="compact"
              hide-details
              accept=".json,application/json"
              prepend-icon="mdi-upload"
              multiple
              show-size
              :disabled="state !== 1"
              @update:modelValue="onMotionUpload"
            ></v-file-input>
            <div class="text-caption">
              Read <a target="_blank" href="https://github.com/Axellwppr/humanoid-policy-viewer?tab=readme-ov-file#add-your-own-robot-policy-and-motions">readme</a> to learn how to create motion JSON files from GMR.<br/>
              Each file should be a single clip (same schema as motions/default.json). File name becomes the motion name (prefixed with [new]). Duplicate names are ignored.
            </div>
            <v-alert
              v-if="motionUploadMessage"
              :type="motionUploadType"
              variant="tonal"
              density="compact"
            >
              {{ motionUploadMessage }}
            </v-alert>
          </template>
        </div>

        <v-divider class="my-2"/>
        <div class="status-legend follow-controls">
          <span class="status-name">Camera follow</span>
          <v-btn
            size="x-small"
            variant="tonal"
            color="primary"
            :disabled="state !== 1"
            @click="toggleCameraFollow"
          >
            {{ cameraFollowEnabled ? 'On' : 'Off' }}
          </v-btn>
        </div>
        <div class="status-legend">
          <span class="status-name">Render scale</span>
          <span class="text-caption">{{ renderScaleLabel }}</span>
          <span class="status-name">Sim Freq</span>
          <span class="text-caption">{{ simStepLabel }}</span>
        </div>
        <v-slider
          v-model="renderScale"
          min="0.5"
          max="2.0"
          step="0.1"
          density="compact"
          hide-details
          @update:modelValue="onRenderScaleChange"
        ></v-slider>
      </v-card-text>
      <v-card-actions>
        <v-btn color="primary" block @click="reset">Reset</v-btn>
      </v-card-actions>
    </v-card>
  </div>
  <v-dialog :model-value="state === 0" persistent max-width="600px" scrollable>
    <v-card title="Loading Simulation Environment">
      <v-card-text>
        <v-progress-linear indeterminate color="primary"></v-progress-linear>
        Loading MuJoCo and ONNX policy, please wait
      </v-card-text>
    </v-card>
  </v-dialog>
  <v-dialog :model-value="state < 0" persistent max-width="600px" scrollable>
    <v-card title="Simulation Environment Loading Error">
      <v-card-text>
        <span v-if="state === -1">
          Unexpected runtime error, please refresh the page.<br />
          {{ extra_error_message }}
        </span>
        <span v-else-if="state === -2">
          Your browser does not support WebAssembly. Please use a recent version of Chrome, Edge, or Firefox.
        </span>
      </v-card-text>
    </v-card>
  </v-dialog>
</template>

<script>
import { MuJoCoDemo } from '@/simulation/main.js';
import loadMujoco from 'mujoco-js';

export default {
  name: 'DemoPage',
  data: () => ({
    state: 0, // 0: loading, 1: running, -1: JS error, -2: wasm unsupported
    extra_error_message: '',
    keydown_listener: null,
    currentMotion: null,
    availableMotions: [],
    trackingState: {
      available: false,
      currentName: 'default',
      currentDone: true,
      refIdx: 0,
      refLen: 0,
      transitionLen: 0,
      motionLen: 0,
      inTransition: false,
      isDefault: true
    },
    trackingTimer: null,
    policies: [
      {
        value: 'g1-tracking-latest',
        title: 'G1 Tracking',
        description: 'Tracking policy with compliance input enabled.',
        policyPath: './examples/checkpoints/g1/tracking_policy_latest.json',
        onnxPath: './examples/checkpoints/g1/policy_latest.onnx'
      }
    ],
    currentPolicy: 'g1-tracking-latest',
    policyLabel: '',
    isPolicyLoading: false,
    policyLoadError: '',
    motionUploadFiles: [],
    motionUploadMessage: '',
    motionUploadType: 'success',
    showUploadOptions: false,
    cameraFollowEnabled: true,
    complianceEnabled: false,
    complianceThreshold: 10.0,
    renderScale: 2.0,
    simStepHz: 0,
    isSmallScreen: false,
    showSmallScreenAlert: true,
    isSafari: false,
    showSafariAlert: true,
    resize_listener: null,
    bridgeWs: null,
    bridgeConnected: false,
    t2mText: '',
    remotePort: 7000,
    configMessage: '',
    configMessageColor: '',
    isApplyingConfig: false,
    t2mLength: 4,
    t2mGenerating: false,
    t2mStatus: '',
    t2mStatusColor: 'text-medium-emphasis',
    fileList: [],
    selectedFile: null,
    selectedFileFolder: 'generated',
    lastSource: null,
    saveMotionName: '',
    isSaving: false,
    showOverwriteDialog: false,
    showClearDialog: false,
    autoReturnDefault: true
  }),
  watch: {
    // Auto-return to default pose when a non-default motion finishes
    'trackingState.currentDone'(done) {
      if (done && this.autoReturnDefault && this.trackingState?.available && !this.trackingState?.isDefault) {
        this.requestMotion('default');
      }
    }
  },
  computed: {
    shouldShowProgress() {
      const state = this.trackingState;
      if (!state || !state.available) {
        return false;
      }
      if (state.refLen > 1) {
        return true;
      }
      return !state.currentDone || !state.isDefault || state.inTransition;
    },
    progressValue() {
      const state = this.trackingState;
      if (!state || state.refLen <= 0) {
        return 0;
      }
      const value = ((state.refIdx + 1) / state.refLen) * 100;
      return Math.max(0, Math.min(100, value));
    },
    showBackToDefault() {
      const state = this.trackingState;
      return state && state.available && !state.isDefault && state.currentDone;
    },
    showMotionLockedNotice() {
      const state = this.trackingState;
      return state && state.available && !state.isDefault && !state.currentDone;
    },
    showMotionSelect() {
      const state = this.trackingState;
      if (!state || !state.available) {
        return false;
      }
      if (!state.isDefault || !state.currentDone) {
        return false;
      }
      return this.motionItems.some((item) => !item.disabled);
    },
    motionItems() {
      const names = [...this.availableMotions].sort((a, b) => {
        if (a === 'default') {
          return -1;
        }
        if (b === 'default') {
          return 1;
        }
        return a.localeCompare(b);
      });
      return names.map((name) => ({
        title: name.split('_')[0],
        value: name,
        disabled: this.isMotionDisabled(name)
      }));
    },
    motionGroups() {
      const items = this.motionItems.filter((item) => item.value !== 'default');
      if (items.length === 0) {
        return [];
      }
      const customized = [];
      const amass = [];
      const gentleHumanoid = [];
      const lafan = [];

      for (const item of items) {
        const value = item.value.toLowerCase();
        if (/(^|[_\s-])gentle$/.test(value)) {
          gentleHumanoid.push(item);
        } else if (value.includes('[new]')) {
          customized.push(item);
        } else if (value.includes('amass')) {
          amass.push(item);
        } else {
          lafan.push(item);
        }
      }

      const groups = [];
      if (lafan.length > 0) {
        groups.push({ title: 'LAFAN1', items: lafan });
      }
      if (amass.length > 0) {
        groups.push({ title: 'AMASS', items: amass });
      }
      if (gentleHumanoid.length > 0) {
        groups.push({ title: 'GentleHumanoid', items: gentleHumanoid });
      }
      if (customized.length > 0) {
        groups.push({ title: 'Customized', items: customized });
      }
      return groups;
    },
    policyItems() {
      return this.policies.map((policy) => ({
        title: policy.title,
        value: policy.value
      }));
    },
    selectedPolicy() {
      return this.policies.find((policy) => policy.value === this.currentPolicy) ?? null;
    },
    policyDescription() {
      return this.selectedPolicy?.description ?? '';
    },
    fileListItems() {
      return this.fileList.map(f => ({ ...f, title: f.name }));
    },
    renderScaleLabel() {
      return `${this.renderScale.toFixed(2)}x`;
    },
    complianceThresholdLabel() {
      return this.complianceThreshold.toFixed(1);
    },
    simStepLabel() {
      if (!this.simStepHz || !Number.isFinite(this.simStepHz)) {
        return '—';
      }
      return `${this.simStepHz.toFixed(1)} Hz`;
    }
  },
  methods: {
    folderChipLabel(folder) {
      if (folder === 'saved') return 'saved';
      if (folder === 'dataset') return 'dataset';
      return 'gen';
    },
    folderChipColor(folder) {
      if (folder === 'saved') return 'success';
      if (folder === 'dataset') return 'info';
      return 'default';
    },
    detectSafari() {
      const ua = navigator.userAgent;
      return /Safari\//.test(ua)
        && !/Chrome\//.test(ua)
        && !/Chromium\//.test(ua)
        && !/Edg\//.test(ua)
        && !/OPR\//.test(ua)
        && !/SamsungBrowser\//.test(ua)
        && !/CriOS\//.test(ua)
        && !/FxiOS\//.test(ua);
    },
    updateScreenState() {
      const isSmall = window.innerWidth < 500 || window.innerHeight < 700;
      if (!isSmall && this.isSmallScreen) {
        this.showSmallScreenAlert = true;
      }
      this.isSmallScreen = isSmall;
    },
    async init() {
      if (typeof WebAssembly !== 'object' || typeof WebAssembly.instantiate !== 'function') {
        this.state = -2;
        return;
      }

      try {
        const mujoco = await loadMujoco();
        this.demo = new MuJoCoDemo(mujoco);
        this.demo.setFollowEnabled?.(this.cameraFollowEnabled);
        await this.demo.init();
        this.demo.main_loop();
        this.demo.params.paused = false;
        this.reapplyCustomMotions();
        this.availableMotions = this.getAvailableMotions();
        this.currentMotion = this.demo.params.current_motion ?? this.availableMotions[0] ?? null;
        this.complianceEnabled = Boolean(this.demo.params?.compliance_enabled);
        const threshold = Number(this.demo.params?.compliance_threshold);
        if (Number.isFinite(threshold)) {
          this.complianceThreshold = threshold;
        }
        this.startTrackingPoll();
        this.renderScale = this.demo.renderScale ?? this.renderScale;
        const matchingPolicy = this.policies.find(
          (policy) => policy.policyPath === this.demo.currentPolicyPath
        );
        if (matchingPolicy) {
          this.currentPolicy = matchingPolicy.value;
        }
        this.policyLabel = this.demo.currentPolicyPath?.split('/').pop() ?? this.policyLabel;
        this.state = 1;
      } catch (error) {
        this.state = -1;
        this.extra_error_message = error.toString();
        console.error(error);
      }
    },
    reapplyCustomMotions() {
      if (!this.demo || !this.customMotions) {
        return;
      }
      const names = Object.keys(this.customMotions);
      if (names.length === 0) {
        return;
      }
      this.addMotions(this.customMotions);
    },
    async onMotionUpload(files) {
      const fileList = Array.isArray(files)
        ? files
        : files instanceof FileList
          ? Array.from(files)
          : files
            ? [files]
            : [];
      if (fileList.length === 0) {
        return;
      }
      if (!this.demo) {
        this.motionUploadMessage = 'Demo not ready yet. Please wait for loading to finish.';
        this.motionUploadType = 'warning';
        this.motionUploadFiles = [];
        return;
      }

      let added = 0;
      let skipped = 0;
      let invalid = 0;
      let failed = 0;
      const prefix = '[new] ';

      for (const file of fileList) {
        try {
          const text = await file.text();
          const parsed = JSON.parse(text);
          const clip = parsed && typeof parsed === 'object' && !Array.isArray(parsed)
            ? parsed
            : null;
          if (!clip) {
            invalid += 1;
            continue;
          }

          const baseName = file.name.replace(/\.[^/.]+$/, '').trim();
          const normalizedName = baseName ? baseName : 'motion';
          const motionName = normalizedName.startsWith(prefix)
            ? normalizedName
            : `${prefix}${normalizedName}`;
          const result = this.addMotions({ [motionName]: clip });
          added += result.added.length;
          skipped += result.skipped.length;
          invalid += result.invalid.length;

          if (result.added.length > 0) {
            if (!this.customMotions) {
              this.customMotions = {};
            }
            for (const name of result.added) {
              this.customMotions[name] = clip;
            }
          }
        } catch (error) {
          console.error('Failed to read motion JSON:', error);
          failed += 1;
        }
      }

      if (added > 0) {
        this.availableMotions = this.getAvailableMotions();
      }

      const parts = [];
      if (added > 0) {
        parts.push(`Added ${added} motion${added === 1 ? '' : 's'}`);
      }
      if (skipped > 0) {
        parts.push(`Skipped ${skipped} duplicate${skipped === 1 ? '' : 's'}`);
      }
      const badCount = invalid + failed;
      if (badCount > 0) {
        parts.push(`Ignored ${badCount} invalid file${badCount === 1 ? '' : 's'}`);
      }
      if (parts.length === 0) {
        this.motionUploadMessage = 'No motions were added.';
        this.motionUploadType = 'info';
      } else {
        this.motionUploadMessage = `${parts.join('. ')}.`;
        this.motionUploadType = badCount > 0 ? 'warning' : 'success';
      }
      this.motionUploadFiles = [];
    },
    toggleCameraFollow() {
      this.cameraFollowEnabled = !this.cameraFollowEnabled;
      if (this.demo?.setFollowEnabled) {
        this.demo.setFollowEnabled(this.cameraFollowEnabled);
      }
    },
    toggleCompliance() {
      const nextEnabled = !this.complianceEnabled;
      if (nextEnabled) {
        const current = this.currentMotion ?? this.demo?.params?.current_motion;
        if (current && !this.isMotionComplianceSuitable(current)) {
          return;
        }
      }
      this.complianceEnabled = nextEnabled;
      this.applyComplianceSettings();
    },
    onComplianceThresholdChange(value) {
      const numeric = Number(value);
      if (!Number.isFinite(numeric)) {
        return;
      }
      this.complianceThreshold = numeric;
      this.applyComplianceSettings();
    },
    applyComplianceSettings() {
      if (!this.demo?.params) {
        return;
      }
      this.demo.params.compliance_enabled = Boolean(this.complianceEnabled);
      this.demo.params.compliance_threshold = Number(this.complianceThreshold);
    },
    isMotionComplianceSuitable(name) {
      const tracking = this.demo?.policyRunner?.tracking ?? null;
      if (!tracking || typeof tracking.isComplianceSuitable !== 'function') {
        return true;
      }
      return tracking.isComplianceSuitable(name);
    },
    isMotionDisabled(name) {
      if (name === 'default') {
        return true;
      }
      if (!this.complianceEnabled) {
        return false;
      }
      return !this.isMotionComplianceSuitable(name);
    },
    onMotionChange(value) {
      if (!this.demo) {
        return;
      }
      if (!value || value === this.demo.params.current_motion) {
        this.currentMotion = this.demo.params.current_motion ?? value;
        return;
      }
      const accepted = this.requestMotion(value);
      if (!accepted) {
        this.currentMotion = this.demo.params.current_motion;
      } else {
        this.currentMotion = value;
        this.updateTrackingState();
      }
    },
    async onPolicyChange(value) {
      if (!this.demo || !value) {
        return;
      }
      const selected = this.policies.find((policy) => policy.value === value);
      if (!selected) {
        return;
      }
      const needsReload = selected.policyPath !== this.demo.currentPolicyPath || selected.onnxPath;
      if (!needsReload) {
        return;
      }
      const wasPaused = this.demo.params?.paused ?? false;
      this.demo.params.paused = true;
      this.isPolicyLoading = true;
      this.policyLoadError = '';
      try {
        await this.demo.reloadPolicy(selected.policyPath, {
          onnxPath: selected.onnxPath || undefined
        });
        this.policyLabel = selected.policyPath?.split('/').pop() ?? this.policyLabel;
        this.reapplyCustomMotions();
        this.availableMotions = this.getAvailableMotions();
        this.currentMotion = this.demo.params.current_motion ?? this.availableMotions[0] ?? null;
        this.updateTrackingState();
      } catch (error) {
        console.error('Failed to reload policy:', error);
        this.policyLoadError = error.toString();
      } finally {
        this.isPolicyLoading = false;
        this.demo.params.paused = wasPaused;
      }
    },
    reset() {
      if (!this.demo) {
        return;
      }
      this.demo.resetSimulation();
      this.availableMotions = this.getAvailableMotions();
      this.currentMotion = this.demo.params.current_motion ?? this.availableMotions[0] ?? null;
      this.updateTrackingState();
    },
    backToDefault() {
      if (!this.demo) {
        return;
      }
      const accepted = this.requestMotion('default');
      if (accepted) {
        this.currentMotion = 'default';
        this.updateTrackingState();
      }
    },
    startTrackingPoll() {
      this.stopTrackingPoll();
      this.updateTrackingState();
      this.updatePerformanceStats();
      this.trackingTimer = setInterval(() => {
        this.updateTrackingState();
        this.updatePerformanceStats();
      }, 33);
    },
    stopTrackingPoll() {
      if (this.trackingTimer) {
        clearInterval(this.trackingTimer);
        this.trackingTimer = null;
      }
    },
    updateTrackingState() {
      const tracking = this.demo?.policyRunner?.tracking ?? null;
      if (!tracking) {
        this.trackingState = {
          available: false,
          currentName: 'default',
          currentDone: true,
          refIdx: 0,
          refLen: 0,
          transitionLen: 0,
          motionLen: 0,
          inTransition: false,
          isDefault: true
        };
        return;
      }
      const state = tracking.playbackState();
      this.trackingState = { ...state };
      this.availableMotions = tracking.availableMotions();
      const current = this.demo.params.current_motion ?? state.currentName ?? null;
      if (current && this.currentMotion !== current) {
        this.currentMotion = current;
      }
    },
    updatePerformanceStats() {
      if (!this.demo) {
        this.simStepHz = 0;
        return;
      }
      this.simStepHz = this.demo.getSimStepHz?.() ?? this.demo.simStepHz ?? 0;
    },
    onRenderScaleChange(value) {
      if (!this.demo) {
        return;
      }
      this.demo.setRenderScale(value);
    },
    getAvailableMotions() {
      const tracking = this.demo?.policyRunner?.tracking ?? null;
      return tracking ? tracking.availableMotions() : [];
    },
    addMotions(motions, options = {}) {
      const tracking = this.demo?.policyRunner?.tracking ?? null;
      if (!tracking) {
        return { added: [], skipped: [], invalid: [] };
      }
      return tracking.addMotions(motions, options);
    },
    requestMotion(name) {
      const tracking = this.demo?.policyRunner?.tracking ?? null;
      if (!tracking || !this.demo) {
        return false;
      }
      const state = this.demo.readPolicyState();
      const accepted = tracking.requestMotion(name, state);
      if (accepted) {
        this.demo.params.current_motion = name;
      }
      return accepted;
    },
    async onSave(overwrite = false) {
      const name = this.saveMotionName.trim();
      if (!name || !this.lastSource) return;
      this.isSaving = true;
      try {
        const resp = await fetch('http://127.0.0.1:8766/save', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ name, source: this.lastSource, overwrite }),
        });
        if (resp.status === 409) {
          this.showOverwriteDialog = true;
        } else if (resp.ok) {
          this.t2mStatus = `Saved: data/saved/${name}.npz`;
          this.t2mStatusColor = 'text-success';
          setTimeout(() => { this.t2mStatus = ''; }, 3000);
        } else {
          const err = await resp.text();
          this.t2mStatus = `Save failed: ${err}`;
          this.t2mStatusColor = 'text-error';
        }
      } catch (e) {
        this.t2mStatus = `Save failed: ${e.message}`;
        this.t2mStatusColor = 'text-error';
      } finally {
        this.isSaving = false;
      }
    },
    async onConfirmOverwrite() {
      this.showOverwriteDialog = false;
      await this.onSave(true);
    },
    async onClearGenerated() {
      this.showClearDialog = false;
      try {
        const resp = await fetch('http://127.0.0.1:8766/clear', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' });
        const data = await resp.json();
        this.t2mStatus = `Deleted ${data.deleted} temp file(s)`;
        this.t2mStatusColor = 'text-medium-emphasis';
        this.lastSource = null;
        this.fileList = this.fileList.filter((f) => f.folder !== 'generated');
        this.selectedFile = null;
        setTimeout(() => { this.t2mStatus = ''; }, 3000);
      } catch (e) {
        this.t2mStatus = `Clear failed: ${e.message}`;
        this.t2mStatusColor = 'text-error';
      }
    },
    onFileSelect(name) {
      const found = this.fileList.find(f => f.name === name);
      if (found) this.selectedFileFolder = found.folder;
    },
    async refreshFileList() {
      try {
        const resp = await fetch('http://127.0.0.1:8766/list');
        this.fileList = await resp.json();
      } catch { this.fileList = []; }
    },
    async onLoadFile() {
      if (!this.selectedFile) return;
      try {
        const resp = await fetch('http://127.0.0.1:8766/load', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ name: this.selectedFile, folder: this.selectedFileFolder }),
        });
        if (!resp.ok) {
          const err = await resp.text();
          this.t2mStatus = `Load failed: ${err}`;
          this.t2mStatusColor = 'text-error';
        }
      } catch (e) {
        this.t2mStatus = `Request failed: ${e.message}`;
        this.t2mStatusColor = 'text-error';
      }
    },
    async fetchConfig() {
      try {
        const resp = await fetch('http://127.0.0.1:8766/config');
        if (resp.ok) {
          const data = await resp.json();
          this.remotePort = data.remote_port ?? 7000;
        }
      } catch (_) {}
    },
    async applyRemotePort() {
      const port = Number(this.remotePort);
      if (!Number.isInteger(port) || port < 1 || port > 65535) {
        this.configMessage = 'Port must be 1–65535';
        this.configMessageColor = 'text-error';
        setTimeout(() => { this.configMessage = ''; }, 3000);
        return;
      }
      this.isApplyingConfig = true;
      this.configMessage = '';
      try {
        const resp = await fetch('http://127.0.0.1:8766/config', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ remote_port: port }),
        });
        if (resp.ok) {
          this.configMessage = 'Switched to remote port ' + port + ', tunnel reconnected';
          this.configMessageColor = 'text-success';
        } else {
          const err = await resp.text();
          this.configMessage = 'Apply failed: ' + err;
          this.configMessageColor = 'text-error';
        }
        setTimeout(() => { this.configMessage = ''; }, 4000);
      } catch (e) {
        this.configMessage = 'Request failed: ' + e.message;
        this.configMessageColor = 'text-error';
        setTimeout(() => { this.configMessage = ''; }, 4000);
      } finally {
        this.isApplyingConfig = false;
      }
    },
    async onGenerate() {
      const text = this.t2mText.trim();
      if (!text || this.t2mGenerating || !this.bridgeConnected) return;
      try {
        const resp = await fetch('http://127.0.0.1:8766/generate', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ text, length: this.t2mLength, steps: 10 }),
        });
        if (!resp.ok) {
          const err = await resp.text();
          this.t2mStatus = err === 'already generating' ? 'Generating, please wait...' : `Error: ${err}`;
          this.t2mStatusColor = 'text-warning';
        }
      } catch (e) {
        this.t2mStatus = `Request failed: ${e.message}`;
        this.t2mStatusColor = 'text-error';
      }
    },
    connectBridge() {
      const url = 'ws://127.0.0.1:8765';
      let ws;
      try {
        ws = new WebSocket(url);
      } catch {
        return;
      }
      this.bridgeWs = ws;
      ws.onopen = () => {
        this.bridgeConnected = true;
        console.log('[bridge] connected');
        this.refreshFileList();
        this.fetchConfig();
      };
      ws.onmessage = (evt) => {
        let msg;
        try { msg = JSON.parse(evt.data); } catch { return; }

        if (msg.type === 'status') {
          this.t2mStatus = msg.message ?? '';
          if (msg.state === 'generating') {
            this.t2mGenerating = true;
            this.t2mStatusColor = 'text-medium-emphasis';
          } else if (msg.state === 'done') {
            this.t2mGenerating = false;
            this.t2mStatusColor = 'text-success';
            setTimeout(() => { this.t2mStatus = ''; }, 3000);
          } else if (msg.state === 'error') {
            this.t2mGenerating = false;
            this.t2mStatusColor = 'text-error';
          }
          return;
        }

        if (msg.type !== 'motion' || !msg.name || !msg.clip) return;
        const prefix = '[T2M] ';
        const motionName = msg.name.startsWith(prefix) ? msg.name : `${prefix}${msg.name}`;
        const result = this.addMotions({ [motionName]: msg.clip }, { overwrite: true });
        if (result.added.length > 0) {
          this.availableMotions = this.getAvailableMotions();
          if (this.demo && this.state === 1) {
            this.requestMotion(motionName);
            this.currentMotion = motionName;
          }
          if (msg.source) {
            this.lastSource = msg.source;
            // pre-fill save name from original text (strip [T2M] prefix)
            this.saveMotionName = msg.name.replace(/^\[T2M\]\s*/, '').trim();
          }
          console.log(`[bridge] loaded motion "${motionName}"`);
        }
      };
      ws.onclose = () => {
        this.bridgeConnected = false;
        this.bridgeWs = null;
        // auto-reconnect every 3s
        setTimeout(() => this.connectBridge(), 3000);
      };
      ws.onerror = () => ws.close();
    }
  },
  mounted() {
    this.customMotions = {};
    this.isSafari = this.detectSafari();
    this.updateScreenState();
    this.resize_listener = () => {
      this.updateScreenState();
    };
    window.addEventListener('resize', this.resize_listener);
    this.init();
    this.connectBridge();
    this.keydown_listener = (event) => {
      if (event.code === 'Backspace') {
        this.reset();
      }
    };
    document.addEventListener('keydown', this.keydown_listener);
  },
  beforeUnmount() {
    this.stopTrackingPoll();
    document.removeEventListener('keydown', this.keydown_listener);
    if (this.resize_listener) {
      window.removeEventListener('resize', this.resize_listener);
    }
    if (this.bridgeWs) {
      this.bridgeWs.onclose = null;  // prevent auto-reconnect
      this.bridgeWs.close();
    }
  }
};
</script>

<style scoped>
.controls {
  position: fixed;
  top: 20px;
  right: 20px;
  width: 320px;
  z-index: 1000;
}

.global-alerts {
  position: fixed;
  top: 20px;
  left: 16px;
  right: 16px;
  max-width: 520px;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  gap: 8px;
  z-index: 1200;
}

.small-screen-alert {
  width: 100%;
}

.safari-alert {
  width: 100%;
}

.controls-card {
  max-height: calc(100vh - 40px);
}

.controls-body {
  max-height: calc(100vh - 160px);
  overflow-y: auto;
  overscroll-behavior: contain;
}

.motion-status {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.motion-groups {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-top: 12px;
  max-height: 200px;
  overflow-y: auto;
}

.motion-group {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
}

.motion-chip {
  text-transform: none;
  font-size: 0.7rem;
}

.status-legend {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}

.status-name {
  font-weight: 600;
}

.policy-file {
  display: block;
  margin-top: 4px;
}


.upload-section {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.upload-toggle {
  padding: 0;
  min-height: unset;
  font-size: 0.85rem;
  text-transform: none;
}

.motion-progress-no-animation,
.motion-progress-no-animation *,
.motion-progress-no-animation::before,
.motion-progress-no-animation::after {
  transition: none !important;
  animation: none !important;
}

.motion-progress-no-animation :deep(.v-progress-linear__determinate),
.motion-progress-no-animation :deep(.v-progress-linear__indeterminate),
.motion-progress-no-animation :deep(.v-progress-linear__background) {
  transition: none !important;
  animation: none !important;
}
</style>
