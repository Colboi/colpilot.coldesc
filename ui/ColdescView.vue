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
const colcontainersStatusError = ref('')
const colcontainersUsername = ref('')
const colcontainersPassword = ref('')
const colcontainersCredentialsDirty = ref(false)
const colcontainersCredentialsSaving = ref(false)
const colcontainersCredentialsMessage = ref('')
const colcontainersCredentialsMessageTone = ref('success')
const colcontainersPollInterval = ref(259200)
const colcontainersRemainingInterval = ref(600)
const colcontainersRenewBefore = ref(3600)
const colcontainersAutoRenew = ref(false)
const colcontainersSettingsDirty = ref(false)
const colcontainersSettingsSaving = ref(false)
const colcontainersSettingsMessage = ref('')
const colcontainersSettingsMessageTone = ref('success')
let colcontainersStatusTimer = null
let colcontainersCountdownTimer = null
let colcontainersStatusLoading = false
let statusReceivedAt = performance.now()
const countdownNow = ref(performance.now())

function applyStatus(nextStatus) {
  statusReceivedAt = performance.now()
  countdownNow.value = statusReceivedAt
  colcontainersStatus.value = nextStatus
  colcontainersStatusError.value = ''
}

async function loadColcontainersStatus() {
  if (colcontainersStatusLoading) return
  colcontainersStatusLoading = true
  try {
    const nextStatus = await props.requestBackend('/api/plugins/coldesc/status')
    applyStatus(nextStatus)
    if (!colcontainersCredentialsDirty.value && !colcontainersCredentialsSaving.value) {
      colcontainersUsername.value = nextStatus.username
    }
    if (!colcontainersSettingsDirty.value && !colcontainersSettingsSaving.value) {
      colcontainersPollInterval.value = nextStatus.container_refresh_interval_seconds
      colcontainersRemainingInterval.value = nextStatus.remaining_refresh_interval_seconds
      colcontainersRenewBefore.value = nextStatus.renew_before_seconds
      colcontainersAutoRenew.value = nextStatus.auto_renew_enabled
    }
  } catch (error) {
    colcontainersStatusError.value = error instanceof Error ? error.message : String(error)
  } finally {
    colcontainersStatusLoading = false
  }
}

function markColcontainersCredentialsDirty() {
  colcontainersCredentialsDirty.value = true
  colcontainersCredentialsMessage.value = ''
}

async function saveColcontainersCredentials() {
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
  try {
    const nextStatus = await props.requestBackend('/api/plugins/coldesc/settings', {
    method: 'POST',
    body: JSON.stringify({
      username,
      password: colcontainersPassword.value,
    }),
    })
    applyStatus(nextStatus)
    colcontainersUsername.value = nextStatus.username
    colcontainersPassword.value = ''
    colcontainersCredentialsDirty.value = false
    colcontainersCredentialsMessageTone.value = 'success'
    colcontainersCredentialsMessage.value = '账号设置已经保存，正在登录 DESC'
  } catch (error) {
    colcontainersCredentialsMessageTone.value = 'error'
    colcontainersCredentialsMessage.value = error instanceof Error ? error.message : String(error)
  } finally {
    colcontainersCredentialsSaving.value = false
  }
}

async function clearColcontainersCredentials() {
  colcontainersCredentialsSaving.value = true
  colcontainersCredentialsMessage.value = ''
  try {
    const nextStatus = await props.requestBackend('/api/plugins/coldesc/settings', {
    method: 'POST',
    body: JSON.stringify({ clear_credentials: true }),
    })
    applyStatus(nextStatus)
    colcontainersUsername.value = ''
    colcontainersPassword.value = ''
    colcontainersCredentialsDirty.value = false
    colcontainersCredentialsMessageTone.value = 'success'
    colcontainersCredentialsMessage.value = '账号信息已经清除'
  } catch (error) {
    colcontainersCredentialsMessageTone.value = 'error'
    colcontainersCredentialsMessage.value = error instanceof Error ? error.message : String(error)
  } finally {
    colcontainersCredentialsSaving.value = false
  }
}

async function retryColcontainersLogin() {
  colcontainersCredentialsSaving.value = true
  colcontainersCredentialsMessage.value = ''
  try {
    applyStatus(await props.requestBackend('/api/plugins/coldesc/settings', {
      method: 'POST', body: JSON.stringify({ retry_login: true }),
    }))
    colcontainersCredentialsMessageTone.value = 'success'
    colcontainersCredentialsMessage.value = '正在重新登录 DESC'
  } catch (error) {
    colcontainersCredentialsMessageTone.value = 'error'
    colcontainersCredentialsMessage.value = error instanceof Error ? error.message : String(error)
  } finally {
    colcontainersCredentialsSaving.value = false
  }
}

async function refreshColcontainers() {
  try {
    applyStatus(await props.requestBackend('/api/plugins/coldesc/settings', {
      method: 'POST', body: JSON.stringify({ refresh_now: true }),
    }))
  } catch (error) {
    colcontainersStatusError.value = error instanceof Error ? error.message : String(error)
  }
}

function markColcontainersSettingsDirty() {
  colcontainersSettingsDirty.value = true
  colcontainersSettingsMessage.value = ''
}

async function saveColcontainersSettings() {
  const pollInterval = Number(colcontainersPollInterval.value)
  const remainingInterval = Number(colcontainersRemainingInterval.value)
  const renewBefore = Number(colcontainersRenewBefore.value)
  if (!Number.isInteger(pollInterval) || pollInterval < 15 || !Number.isInteger(remainingInterval) || remainingInterval < 15) {
    colcontainersSettingsMessageTone.value = 'error'
    colcontainersSettingsMessage.value = '两个获取间隔都必须至少为 15 秒'
    return
  }
  if (!Number.isInteger(renewBefore) || renewBefore < 0) {
    colcontainersSettingsMessageTone.value = 'error'
    colcontainersSettingsMessage.value = '续约阈值必须为零或更大的整数秒数'
    return
  }

  colcontainersSettingsSaving.value = true
  colcontainersSettingsMessage.value = ''
  try {
    const nextStatus = await props.requestBackend('/api/plugins/coldesc/settings', {
    method: 'POST',
    body: JSON.stringify({
      container_refresh_interval_seconds: pollInterval,
      remaining_refresh_interval_seconds: remainingInterval,
      renew_before_seconds: renewBefore,
      auto_renew_enabled: colcontainersAutoRenew.value,
    }),
    })
    applyStatus(nextStatus)
    colcontainersPollInterval.value = nextStatus.container_refresh_interval_seconds
    colcontainersRemainingInterval.value = nextStatus.remaining_refresh_interval_seconds
    colcontainersRenewBefore.value = nextStatus.renew_before_seconds
    colcontainersAutoRenew.value = nextStatus.auto_renew_enabled
    colcontainersSettingsDirty.value = false
    colcontainersSettingsMessageTone.value = 'success'
    colcontainersSettingsMessage.value = '同步设置已经保存'
  } catch (error) {
    colcontainersSettingsMessageTone.value = 'error'
    colcontainersSettingsMessage.value = error instanceof Error ? error.message : String(error)
  } finally {
    colcontainersSettingsSaving.value = false
  }
}

function remainingSeconds(container) {
  const remaining = Date.parse(container.expires_at) - Date.parse(colcontainersStatus.value.server_time)
  return Math.max(0, Math.ceil((remaining - (countdownNow.value - statusReceivedAt)) / 1000))
}

function remainingDisplay(container) {
  const total = remainingSeconds(container)
  const days = Math.floor(total / 86400)
  const hours = Math.floor(total % 86400 / 3600)
  const minutes = Math.floor(total % 3600 / 60)
  const seconds = total % 60
  const clock = [hours, minutes, seconds].map((value) => String(value).padStart(2, '0')).join(':')
  return days > 0 ? `${days} 天 ${clock}` : clock
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
  colcontainersCountdownTimer = window.setInterval(() => { countdownNow.value = performance.now() }, 1000)
})

onBeforeUnmount(() => {
  if (colcontainersStatusTimer !== null) {
    window.clearInterval(colcontainersStatusTimer)
  }
  if (colcontainersCountdownTimer !== null) {
    window.clearInterval(colcontainersCountdownTimer)
  }
})
</script>

<template>
  <div class="colcontainers-content">
    <div v-if="colcontainersStatusError" class="colcontainers-error" role="alert">
      <strong>DESC 状态读取失败</strong>
      <span>{{ colcontainersStatusError }}</span>
      <button type="button" class="secondary-button" @click="loadColcontainersStatus">重试读取</button>
    </div>
    <div v-if="!colcontainersStatus" class="colcontainers-loading">
      <div class="loader"></div>
      <span>正在读取 DESC 容器状态</span>
    </div>

    <template v-else>
      <div v-if="colcontainersStatus.last_error" class="colcontainers-error" :class="{ 'is-login': colcontainersStatus.login_failed }" role="alert">
        <strong>{{ colcontainersStatus.login_failed ? '请检查登录信息' : 'DESC 同步出现问题' }}</strong>
        <span>{{ colcontainersStatus.last_error }}</span>
      </div>

      <div class="colcontainers-summary-grid">
        <article class="colcontainers-summary-card">
          <span>登录状态</span>
          <strong>{{ colcontainersStatus.login_failed ? '等待重新登录' : colcontainersStatus.authenticated ? '已经登录' : '等待登录' }}</strong>
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
          <form class="colcontainers-credentials-form" @submit.prevent="saveColcontainersCredentials">
            <label>
              <span>账号</span>
              <input
                v-model="colcontainersUsername"
                type="text"
                autocomplete="username"
                aria-label="DESC 账号"
                :disabled="colcontainersCredentialsSaving"
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
                :disabled="colcontainersCredentialsSaving"
                @input="markColcontainersCredentialsDirty"
              />
            </label>
          <div class="colcontainers-panel-actions">
            <button type="submit" :disabled="colcontainersCredentialsSaving">
              {{ colcontainersCredentialsSaving ? '保存中' : '保存账号' }}
            </button>
            <button type="button" class="secondary-button" :disabled="colcontainersCredentialsSaving || !colcontainersStatus.credentials_configured" @click="retryColcontainersLogin">重新登录</button>
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
          </form>
        </section>

        <section class="colcontainers-panel">
          <div class="colcontainers-panel-heading">
            <div>
              <strong>信息刷新与自动续约</strong>
              <span>容器资料与剩余时间分别获取，登录后立即获取完整信息。</span>
            </div>
          </div>
          <label class="colcontainers-toggle-row">
            <input v-model="colcontainersAutoRenew" type="checkbox" @change="markColcontainersSettingsDirty" />
            <span>启用自动续约</span>
          </label>
          <div class="colcontainers-number-form">
            <label>
              <span>容器资料获取间隔</span>
              <input
                v-model.number="colcontainersPollInterval"
                type="number"
                min="15"
                step="1"
                aria-label="容器资料获取间隔秒数"
                @input="markColcontainersSettingsDirty"
              />
              <small>秒</small>
            </label>
            <label>
              <span>剩余时间获取间隔</span>
              <input v-model.number="colcontainersRemainingInterval" type="number" min="15" step="1" aria-label="剩余时间获取间隔秒数" @input="markColcontainersSettingsDirty" />
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
            <span>倒计时每秒更新，远端剩余时间每 {{ colcontainersStatus.remaining_refresh_interval_seconds }} 秒获取。</span>
          </div>
          <button type="button" class="secondary-button" :disabled="colcontainersStatus.syncing || colcontainersCredentialsSaving || !colcontainersStatus.credentials_configured" @click="refreshColcontainers">{{ colcontainersStatus.syncing ? '正在获取' : '立即获取信息' }}</button>
        </div>
        <div v-if="colcontainersStatus.containers.length === 0" class="colcontainers-empty">
          {{ colcontainersStatus.syncing ? '正在获取容器信息' : !colcontainersStatus.authenticated ? '登录后显示当前账号的容器' : '当前账号没有容器数据' }}
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
              <strong class="colcontainers-countdown" :data-remaining-seconds="remainingSeconds(container)">{{ remainingDisplay(container) }}</strong>
            </div>
            <div class="colcontainers-container-info">
              <span>预计到期：{{ formatDate(container.expires_at) }}</span>
              <span>时间获取：{{ formatDate(container.checked_at) }}</span>
              <span>资料获取：{{ formatDate(container.metadata_checked_at) }}</span>
              <span>{{ container.renewal_detail }}</span>
            </div>
            <div class="colcontainers-container-meta">
              <span>内网 IP：{{ container.ip || '尚未分配' }}</span>
              <span>CPU：{{ container.cpu || '未提供' }}</span>
              <span>内存：{{ container.memory || '未提供' }}</span>
              <span>存储：{{ container.storage || '未提供' }}</span>
              <span>GPU：{{ container.gpu || '未提供' }}</span>
              <span>系统：{{ container.operating_system || '未提供' }}</span>
              <span v-if="container.server_description">节点说明：{{ container.server_description }}</span>
              <span>备注：{{ container.remarks || '没有备注' }}</span>
            </div>
          </article>
        </div>
      </section>
    </template>
  </div>
</template>
