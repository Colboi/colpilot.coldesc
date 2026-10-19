<script setup>
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'

import './style.css'

const props = defineProps({
  plugin: {
    type: Object,
    required: true,
  },
  requestBackend: {
    type: Function,
    required: true,
  },
})

const colcontainersStatus = ref(null)
const colcontainersUsername = ref('')
const colcontainersPassword = ref('')
const colcontainersCredentialsDirty = ref(false)
const colcontainersCredentialsSaving = ref(false)
const colcontainersCredentialsMessage = ref('')
const colcontainersCredentialsMessageTone = ref('success')
const colcontainersPollInterval = ref(60)
const colcontainersRenewBefore = ref(3600)
const colcontainersAutoRenew = ref(false)
const colcontainersSettingsDirty = ref(false)
const colcontainersSettingsSaving = ref(false)
const colcontainersSettingsMessage = ref('')
const colcontainersSettingsMessageTone = ref('success')
let colcontainersStatusTimer = null

function loadColcontainersStatus() {
  return props.requestBackend('/api/plugins/coldesc/status').then((nextStatus) => {
    colcontainersStatus.value = nextStatus
    if (!colcontainersCredentialsDirty.value && !colcontainersCredentialsSaving.value) {
      colcontainersUsername.value = nextStatus.username
    }
    if (!colcontainersSettingsDirty.value && !colcontainersSettingsSaving.value) {
      colcontainersPollInterval.value = nextStatus.poll_interval_seconds
      colcontainersRenewBefore.value = nextStatus.renew_before_seconds
      colcontainersAutoRenew.value = nextStatus.auto_renew_enabled
    }
  })
}

function markColcontainersCredentialsDirty() {
  colcontainersCredentialsDirty.value = true
  colcontainersCredentialsMessage.value = ''
}

function saveColcontainersCredentials() {
  const username = colcontainersUsername.value.trim()
  if (!username) {
    colcontainersCredentialsMessageTone.value = 'error'
    colcontainersCredentialsMessage.value = '请输入 DESC 账号'
    return
  }
  if (!colcontainersPassword.value && !colcontainersStatus.value?.password_configured) {
    colcontainersCredentialsMessageTone.value = 'error'
    colcontainersCredentialsMessage.value = '请输入 DESC 密码'
    return
  }

  colcontainersCredentialsSaving.value = true
  colcontainersCredentialsMessage.value = ''
  props.requestBackend('/api/plugins/coldesc/settings', {
    method: 'POST',
    body: JSON.stringify({
      username,
      password: colcontainersPassword.value,
    }),
  }).then((nextStatus) => {
    colcontainersStatus.value = nextStatus
    colcontainersUsername.value = nextStatus.username
    colcontainersPassword.value = ''
    colcontainersCredentialsDirty.value = false
    colcontainersCredentialsMessageTone.value = 'success'
    colcontainersCredentialsMessage.value = '账号设置已经保存，正在登录 DESC'
  }).finally(() => {
    colcontainersCredentialsSaving.value = false
  })
}

function clearColcontainersCredentials() {
  colcontainersCredentialsSaving.value = true
  colcontainersCredentialsMessage.value = ''
  props.requestBackend('/api/plugins/coldesc/settings', {
    method: 'POST',
    body: JSON.stringify({ clear_credentials: true }),
  }).then((nextStatus) => {
    colcontainersStatus.value = nextStatus
    colcontainersUsername.value = ''
    colcontainersPassword.value = ''
    colcontainersCredentialsDirty.value = false
    colcontainersCredentialsMessageTone.value = 'success'
    colcontainersCredentialsMessage.value = '账号信息已经清除'
  }).finally(() => {
    colcontainersCredentialsSaving.value = false
  })
}

function markColcontainersSettingsDirty() {
  colcontainersSettingsDirty.value = true
  colcontainersSettingsMessage.value = ''
}

function saveColcontainersSettings() {
  const pollInterval = Number(colcontainersPollInterval.value)
  const renewBefore = Number(colcontainersRenewBefore.value)
  if (!Number.isInteger(pollInterval) || pollInterval < 15) {
    colcontainersSettingsMessageTone.value = 'error'
    colcontainersSettingsMessage.value = '同步周期必须至少为 15 秒'
    return
  }
  if (!Number.isInteger(renewBefore) || renewBefore < 0) {
    colcontainersSettingsMessageTone.value = 'error'
    colcontainersSettingsMessage.value = '续约阈值必须为零或更大的整数秒数'
    return
  }

  colcontainersSettingsSaving.value = true
  colcontainersSettingsMessage.value = ''
  props.requestBackend('/api/plugins/coldesc/settings', {
    method: 'POST',
    body: JSON.stringify({
      poll_interval_seconds: pollInterval,
      renew_before_seconds: renewBefore,
      auto_renew_enabled: colcontainersAutoRenew.value,
    }),
  }).then((nextStatus) => {
    colcontainersStatus.value = nextStatus
    colcontainersPollInterval.value = nextStatus.poll_interval_seconds
    colcontainersRenewBefore.value = nextStatus.renew_before_seconds
    colcontainersAutoRenew.value = nextStatus.auto_renew_enabled
    colcontainersSettingsDirty.value = false
    colcontainersSettingsMessageTone.value = 'success'
    colcontainersSettingsMessage.value = '同步设置已经保存'
  }).finally(() => {
    colcontainersSettingsSaving.value = false
  })
}

function formatDate(value) {
  if (!value) {
    return '尚未获取'
  }
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) {
    return '时间格式错误'
  }
  return date.toLocaleString('zh-CN', {
    hour12: false,
  })
}

function renewalLabel(status) {
  return {
    monitoring: '正在监控',
    attention: '需要续约',
    renewed: '已经续约',
    waiting: '等待确认',
  }[status] ?? '等待同步'
}

function renewalTone(status) {
  if (status === 'renewed') {
    return 'success'
  }
  if (status === 'attention') {
    return 'danger'
  }
  if (status === 'waiting') {
    return 'warning'
  }
  return 'normal'
}

watch(
  () => props.plugin.enabled,
  () => {
    loadColcontainersStatus()
  },
)

onMounted(() => {
  loadColcontainersStatus()
  colcontainersStatusTimer = window.setInterval(loadColcontainersStatus, 5000)
})

onBeforeUnmount(() => {
  if (colcontainersStatusTimer !== null) {
    window.clearInterval(colcontainersStatusTimer)
  }
})
</script>

<template>
  <div class="colcontainers-content">
    <div v-if="!colcontainersStatus" class="colcontainers-loading">
      <div class="loader"></div>
      <span>正在读取 DESC 容器状态</span>
    </div>

    <template v-else>
      <div v-if="colcontainersStatus.last_error" class="colcontainers-error">
        <strong>DESC 同步出现问题</strong>
        <span>{{ colcontainersStatus.last_error }}</span>
      </div>

      <div class="colcontainers-summary-grid">
        <article class="colcontainers-summary-card">
          <span>登录状态</span>
          <strong>{{ colcontainersStatus.authenticated ? '已经登录' : '等待登录' }}</strong>
          <small>{{ colcontainersStatus.authenticated ? '后台会在认证失效时自动登录' : '请填写账号和密码' }}</small>
        </article>
        <article class="colcontainers-summary-card">
          <span>容器数量</span>
          <strong>{{ colcontainersStatus.containers.length }}</strong>
          <small>最近同步：{{ formatDate(colcontainersStatus.last_success_at) }}</small>
        </article>
        <article class="colcontainers-summary-card">
          <span>自动续约</span>
          <strong>{{ colcontainersStatus.auto_renew_enabled ? '已经启用' : '已经停用' }}</strong>
          <small>阈值：{{ colcontainersStatus.renew_before_seconds }} 秒</small>
        </article>
      </div>

      <div class="colcontainers-settings-grid">
        <section class="colcontainers-panel">
          <div class="colcontainers-panel-heading">
            <div>
              <strong>DESC 登录账号</strong>
              <span>密码只写入本地插件设置，不会显示在状态页面。</span>
            </div>
          </div>
          <div class="colcontainers-credentials-form">
            <label>
              <span>账号</span>
              <input
                v-model="colcontainersUsername"
                type="text"
                autocomplete="username"
                aria-label="DESC 账号"
                @input="markColcontainersCredentialsDirty"
              />
            </label>
            <label>
              <span>密码</span>
              <input
                v-model="colcontainersPassword"
                type="password"
                autocomplete="current-password"
                placeholder="留空保持当前密码"
                aria-label="DESC 密码"
                @input="markColcontainersCredentialsDirty"
              />
            </label>
          </div>
          <div class="colcontainers-panel-actions">
            <button type="button" :disabled="colcontainersCredentialsSaving" @click="saveColcontainersCredentials">
              {{ colcontainersCredentialsSaving ? '保存中' : '保存账号' }}
            </button>
            <button
              type="button"
              class="secondary-button"
              :disabled="colcontainersCredentialsSaving || !colcontainersStatus.credentials_configured"
              @click="clearColcontainersCredentials"
            >
              清除账号信息
            </button>
            <span
              v-if="colcontainersCredentialsMessage"
              class="colcontainers-message"
              :class="`is-${colcontainersCredentialsMessageTone}`"
            >
              {{ colcontainersCredentialsMessage }}
            </span>
          </div>
        </section>

        <section class="colcontainers-panel">
          <div class="colcontainers-panel-heading">
            <div>
              <strong>自动续约设置</strong>
              <span>后台会按照同步周期读取容器剩余时间。</span>
            </div>
          </div>
          <label class="colcontainers-toggle-row">
            <input v-model="colcontainersAutoRenew" type="checkbox" @change="markColcontainersSettingsDirty" />
            <span>启用自动续约</span>
          </label>
          <div class="colcontainers-number-form">
            <label>
              <span>同步周期</span>
              <input
                v-model.number="colcontainersPollInterval"
                type="number"
                min="15"
                step="1"
                aria-label="同步周期秒数"
                @input="markColcontainersSettingsDirty"
              />
              <small>秒</small>
            </label>
            <label>
              <span>续约阈值</span>
              <input
                v-model.number="colcontainersRenewBefore"
                type="number"
                min="0"
                step="1"
                aria-label="续约阈值秒数"
                @input="markColcontainersSettingsDirty"
              />
              <small>秒</small>
            </label>
          </div>
          <div class="colcontainers-panel-actions">
            <button type="button" :disabled="colcontainersSettingsSaving" @click="saveColcontainersSettings">
              {{ colcontainersSettingsSaving ? '保存中' : '保存设置' }}
            </button>
            <span
              v-if="colcontainersSettingsMessage"
              class="colcontainers-message"
              :class="`is-${colcontainersSettingsMessageTone}`"
            >
              {{ colcontainersSettingsMessage }}
            </span>
          </div>
        </section>
      </div>

      <section class="colcontainers-panel colcontainers-container-panel">
        <div class="colcontainers-panel-heading colcontainers-container-heading">
          <div>
            <strong>容器剩余时间</strong>
            <span>页面每 5 秒读取一次本地同步结果。</span>
          </div>
          <button type="button" class="secondary-button" @click="loadColcontainersStatus">立即刷新</button>
        </div>
        <div v-if="colcontainersStatus.containers.length === 0" class="colcontainers-empty">
          {{ colcontainersStatus.credentials_configured ? '当前账号没有容器数据' : '登录后显示当前账号的容器' }}
        </div>
        <div v-else class="colcontainers-container-grid">
          <article
            v-for="container in colcontainersStatus.containers"
            :key="container.cid"
            class="colcontainers-container-card"
            :class="`is-${renewalTone(container.renewal_status)}`"
          >
            <div class="colcontainers-container-topline">
              <div>
                <strong>{{ container.name }}</strong>
                <span>{{ container.server }}</span>
              </div>
              <span class="colcontainers-renewal-label">{{ renewalLabel(container.renewal_status) }}</span>
            </div>
            <div class="colcontainers-remaining">
              <span>剩余时间</span>
              <strong>{{ container.remaining_display }}</strong>
            </div>
            <div class="colcontainers-container-info">
              <span>预计到期：{{ formatDate(container.expires_at) }}</span>
              <span>最近检查：{{ formatDate(container.checked_at) }}</span>
              <span>{{ container.renewal_detail }}</span>
            </div>
            <div class="colcontainers-container-meta">
              <span>内网 IP：{{ container.ip || '尚未分配' }}</span>
              <span>备注：{{ container.remarks || '没有备注' }}</span>
            </div>
          </article>
        </div>
      </section>
    </template>
  </div>
</template>
