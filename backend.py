import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx

from . import PLUGIN_ID


SERVICE_BASE_URL = 'http://desc.snrc.site/api'
DEFAULT_SETTINGS: dict[str, object] = {
    'username': '',
    'password': '',
    'poll_interval_seconds': 60,
    'renew_before_seconds': 3600,
    'auto_renew_enabled': False,
}
SUPPORTED_SETTINGS = {
    'username',
    'password',
    'poll_interval_seconds',
    'renew_before_seconds',
    'auto_renew_enabled',
    'clear_credentials',
}
RENEWAL_RETRY_COOLDOWN_SECONDS = 300
HTTP_TIMEOUT_SECONDS = 20.0


class ColdescPlugin:
    plugin_id = PLUGIN_ID

    def __init__(self, plugin_root: Path, config_store: Any) -> None:
        self.root = plugin_root
        self.config_store = config_store
        self.legacy_settings_path = plugin_root / 'settings.json'
        self._migrate_legacy_settings()
        self.client = httpx.Client(
            base_url=SERVICE_BASE_URL,
            timeout=HTTP_TIMEOUT_SECONDS,
        )
        self.lock = threading.RLock()
        self.stop_event = threading.Event()
        self.thread: threading.Thread | None = None
        self.token: str | None = None
        self.user_id: int | str | None = None
        self.authenticated = False
        self.containers: list[dict[str, object]] = []
        self.renewal_states: dict[str, dict[str, object]] = {}
        self.last_error: str | None = None
        self.last_success_at: str | None = None
        self.updated_at: str | None = None

    def start(self) -> None:
        with self.lock:
            settings = self._read_settings_locked()
            if not self._credentials_configured(settings):
                return
            if self.thread is not None and self.thread.is_alive():
                return
            self.stop_event = threading.Event()
            self.last_error = None
            self.thread = threading.Thread(
                target=self._run,
                name='coldesc-sync',
                daemon=True,
            )
            self.thread.start()

    def stop(self) -> None:
        with self.lock:
            thread = self.thread
            self.stop_event.set()
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=HTTP_TIMEOUT_SECONDS + 5)
        with self.lock:
            if self.thread is thread and (thread is None or not thread.is_alive()):
                self.thread = None

    def runtime_status(self) -> dict[str, object]:
        with self.lock:
            settings = self._read_settings_locked()
            thread = self.thread
            stop_requested = self.stop_event.is_set()
            if thread is not None and thread.is_alive():
                return {
                    'status': 'running',
                    'detail': 'DESC 容器同步正在后台运行',
                    'exit_code': None,
                }
            if not self._credentials_configured(settings):
                return {
                    'status': 'stopped',
                    'detail': '请填写 DESC 账号和密码',
                    'exit_code': None,
                }
            if thread is not None and not stop_requested:
                return {
                    'status': 'error',
                    'detail': self.last_error or 'DESC 容器同步线程已经停止',
                    'exit_code': None,
                }
            return {
                'status': 'stopped',
                'detail': 'DESC 容器同步已经停止',
                'exit_code': None,
            }

    def status(self, enabled: bool) -> dict[str, object]:
        del enabled
        with self.lock:
            settings = self._read_settings_locked()
            containers = [dict(item) for item in self.containers]
            authenticated = self.authenticated
            last_error = self.last_error
            last_success_at = self.last_success_at
            updated_at = self.updated_at
        runtime = self.runtime_status()
        return {
            'username': str(settings['username']),
            'credentials_configured': self._credentials_configured(settings),
            'password_configured': bool(str(settings['password'])),
            'login_required': not authenticated,
            'authenticated': authenticated,
            'auto_renew_enabled': bool(settings['auto_renew_enabled']),
            'poll_interval_seconds': int(settings['poll_interval_seconds']),
            'renew_before_seconds': int(settings['renew_before_seconds']),
            'containers': containers,
            'last_error': last_error,
            'last_success_at': last_success_at,
            'updated_at': updated_at,
            'runtime': runtime,
        }

    def update_settings(self, settings: dict[str, object], enabled: bool) -> None:
        unknown_keys = sorted(set(settings) - SUPPORTED_SETTINGS)
        if unknown_keys:
            raise ValueError(f'unsupported settings: {", ".join(unknown_keys)}')
        if not settings:
            raise ValueError('settings must not be empty')

        with self.lock:
            current = self._read_settings_locked()
            updated = dict(current)
            clear_credentials = settings.get('clear_credentials', False)
            if not isinstance(clear_credentials, bool):
                raise ValueError('clear_credentials must be a boolean')
            if clear_credentials:
                updated['username'] = ''
                updated['password'] = ''
            if 'username' in settings:
                username = settings['username']
                if not isinstance(username, str):
                    raise ValueError('username must be a string')
                updated['username'] = username
            if 'password' in settings:
                password = settings['password']
                if not isinstance(password, str):
                    raise ValueError('password must be a string')
                if password or not self._credentials_configured(current):
                    updated['password'] = password
            if 'poll_interval_seconds' in settings:
                updated['poll_interval_seconds'] = settings['poll_interval_seconds']
            if 'renew_before_seconds' in settings:
                updated['renew_before_seconds'] = settings['renew_before_seconds']
            if 'auto_renew_enabled' in settings:
                updated['auto_renew_enabled'] = settings['auto_renew_enabled']
            self._validate_settings(updated)
            changed = updated != current
            credentials_changed = (
                updated['username'] != current['username']
                or updated['password'] != current['password']
            )
            if changed:
                self.config_store.update_section(
                    self.plugin_id,
                    updated,
                )
            if credentials_changed:
                self._clear_auth_locked()
                self.containers = []
                self.renewal_states = {}
            should_start = bool(enabled) and self._credentials_configured(updated)

        if changed:
            self.stop()
            if should_start:
                self.start()

    def _run(self) -> None:
        while not self.stop_event.is_set():
            settings = self._read_settings()
            if not self._credentials_configured(settings):
                return
            next_containers = self._synchronize(settings)
            now = self._now()
            with self.lock:
                self.containers = next_containers
                self.authenticated = self.token is not None and self.user_id is not None
                self.last_success_at = now
                self.updated_at = now
                self.last_error = None
            if self.stop_event.wait(int(settings['poll_interval_seconds'])):
                return

    def _synchronize(self, settings: dict[str, object]) -> list[dict[str, object]]:
        self._ensure_authenticated(settings)
        with self.lock:
            user_id = self.user_id
        if user_id is None:
            raise RuntimeError('DESC 用户编号缺失')
        response = self._authenticated_request(
            'GET',
            '/container/ofuser',
            params={'uid': user_id},
            allowed_statuses={404},
        )
        payload = [] if response.status_code == 404 else response.json()
        if not isinstance(payload, list):
            raise ValueError('DESC 容器列表响应格式错误')

        containers: list[dict[str, object]] = []
        for item in payload:
            containers.append(self._build_container_state(item, settings))
        return containers

    def _build_container_state(
        self,
        item: object,
        settings: dict[str, object],
    ) -> dict[str, object]:
        if not isinstance(item, dict):
            raise ValueError('DESC 容器记录格式错误')
        cid = self._container_id(item.get('cid'))
        name = item.get('name')
        if not isinstance(name, str) or not name:
            raise ValueError('DESC 容器名称缺失')
        machine = item.get('Machine')
        if not isinstance(machine, dict):
            machine = {}
        server = machine.get('name') or item.get('server')
        if not isinstance(server, str) or not server:
            raise ValueError(f'DESC 容器节点缺失：{name}')

        remaining_seconds = self._get_remaining_seconds(server, name)
        renewal_status = 'monitoring'
        renewal_detail = '当前剩余时间高于自动续约阈值'
        renewed_at: object = None
        renewal_key = str(cid)
        previous_state = self._read_renewal_state(renewal_key)
        if isinstance(previous_state.get('last_renewed_at'), str):
            renewed_at = previous_state['last_renewed_at']

        renew_before_seconds = int(settings['renew_before_seconds'])
        auto_renew_enabled = bool(settings['auto_renew_enabled'])
        if remaining_seconds <= renew_before_seconds:
            if not auto_renew_enabled:
                renewal_status = 'attention'
                renewal_detail = '已经进入续约阈值，请开启自动续约'
            elif self._renewal_is_due(previous_state):
                self._renew_container(cid)
                renewed_at = self._now()
                self._write_renewal_state(
                    renewal_key,
                    {
                        'last_attempt_at': datetime.now(timezone.utc),
                        'last_renewed_at': renewed_at,
                    },
                )
                remaining_seconds = self._get_remaining_seconds(server, name)
                renewal_status = 'renewed'
                renewal_detail = '自动续约成功'
            else:
                renewal_status = 'waiting'
                renewal_detail = '已经提交续约，等待新的剩余时间'

        checked_at = self._now()
        return {
            'cid': cid,
            'name': name,
            'server': server,
            'ip': item.get('ip') if isinstance(item.get('ip'), str) else None,
            'remarks': item.get('remarks') if isinstance(item.get('remarks'), str) else '',
            'remaining_seconds': remaining_seconds,
            'remaining_display': self._format_duration(remaining_seconds),
            'expires_at': (
                datetime.now(timezone.utc) + timedelta(seconds=remaining_seconds)
            ).isoformat(),
            'checked_at': checked_at,
            'renewal_status': renewal_status,
            'renewal_detail': renewal_detail,
            'last_renewed_at': renewed_at,
        }

    def _get_remaining_seconds(self, server: str, container_name: str) -> int:
        server_path = quote(server, safe='')
        container_path = quote(container_name, safe='')
        response = self._authenticated_request(
            'GET',
            f'/incus/{server_path}/when/{container_path}',
        )
        content_type = response.headers.get('content-type', '').lower()
        value: object = response.json() if 'json' in content_type else response.text.strip()
        return self._coerce_seconds(value)

    def _renew_container(self, cid: int | str) -> None:
        self._authenticated_request(
            'PUT',
            '/container/renew',
            params={'cid': cid},
        )

    def _ensure_authenticated(self, settings: dict[str, object]) -> None:
        with self.lock:
            has_auth = self.token is not None and self.user_id is not None
        if not has_auth:
            self._authenticate(settings)

    def _authenticate(self, settings: dict[str, object]) -> None:
        response = self.client.post(
            '/user/validate',
            json={
                'username': settings['username'],
                'password': settings['password'],
            },
        )
        if response.status_code >= 400:
            self._set_error(f'DESC 登录请求失败：HTTP {response.status_code}')
            response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict) or payload.get('valid') is not True:
            self._set_error('DESC 登录失败：账号或密码错误')
            raise ValueError('DESC 登录失败：账号或密码错误')
        token = payload.get('token')
        if not isinstance(token, str) or not token:
            self._set_error('DESC 登录失败：服务端没有返回 token')
            raise ValueError('DESC 登录失败：服务端没有返回 token')

        users_response = self.client.get(
            '/users',
            headers={'Authorization': f'Bearer {token}'},
        )
        if users_response.status_code >= 400:
            self._set_error(f'DESC 用户信息请求失败：HTTP {users_response.status_code}')
            users_response.raise_for_status()
        users = users_response.json()
        if not isinstance(users, list):
            raise ValueError('DESC 用户信息响应格式错误')
        username = str(settings['username'])
        user = next(
            (
                candidate
                for candidate in users
                if isinstance(candidate, dict) and candidate.get('username') == username
            ),
            None,
        )
        if not isinstance(user, dict):
            self._set_error('DESC 登录失败：用户信息中没有当前账号')
            raise ValueError('DESC 登录失败：用户信息中没有当前账号')
        user_id = user.get('uid')
        if isinstance(user_id, bool) or not isinstance(user_id, (int, str)):
            raise ValueError('DESC 用户编号格式错误')
        with self.lock:
            self.token = token
            self.user_id = user_id
            self.authenticated = True

    def _authenticated_request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, object] | None = None,
        allowed_statuses: set[int] | None = None,
    ) -> httpx.Response:
        self._ensure_authenticated(self._read_settings())
        with self.lock:
            token = self.token
        if token is None:
            raise RuntimeError('DESC token 缺失')
        response = self.client.request(
            method,
            path,
            params=params,
            headers={'Authorization': f'Bearer {token}'},
        )
        if response.status_code == 401:
            with self.lock:
                self._clear_auth_locked()
            self._authenticate(self._read_settings())
            with self.lock:
                token = self.token
            if token is None:
                raise RuntimeError('DESC token 缺失')
            response = self.client.request(
                method,
                path,
                params=params,
                headers={'Authorization': f'Bearer {token}'},
            )
        if response.status_code >= 400 and (
            allowed_statuses is None or response.status_code not in allowed_statuses
        ):
            self._set_error(f'DESC 请求失败：HTTP {response.status_code}')
            response.raise_for_status()
        return response

    def _read_settings(self) -> dict[str, object]:
        with self.lock:
            return self._read_settings_locked()

    def _read_settings_locked(self) -> dict[str, object]:
        raw_settings = self.config_store.read_section(self.plugin_id)
        unknown_keys = sorted(set(raw_settings) - set(DEFAULT_SETTINGS))
        if unknown_keys:
            raise ValueError(f'unsupported saved settings: {", ".join(unknown_keys)}')
        settings = dict(DEFAULT_SETTINGS)
        if 'username' in raw_settings:
            settings['username'] = raw_settings['username']
        if 'password' in raw_settings:
            settings['password'] = raw_settings['password']
        if 'poll_interval_seconds' in raw_settings:
            settings['poll_interval_seconds'] = self._parse_integer(
                raw_settings['poll_interval_seconds'],
                'poll_interval_seconds',
            )
        if 'renew_before_seconds' in raw_settings:
            settings['renew_before_seconds'] = self._parse_integer(
                raw_settings['renew_before_seconds'],
                'renew_before_seconds',
            )
        if 'auto_renew_enabled' in raw_settings:
            settings['auto_renew_enabled'] = self._parse_boolean(
                raw_settings['auto_renew_enabled'],
                'auto_renew_enabled',
            )
        self._validate_settings(settings)
        return settings

    def _migrate_legacy_settings(self) -> None:
        self.config_store.migrate_json_section(
            self.plugin_id,
            self.legacy_settings_path,
            set(DEFAULT_SETTINGS),
        )

    @staticmethod
    def _parse_integer(value: str, key: str) -> int:
        try:
            return int(value.strip())
        except ValueError as error:
            raise ValueError(f'{key} must be an integer') from error

    @staticmethod
    def _parse_boolean(value: str, key: str) -> bool:
        normalised = value.strip().lower()
        if normalised in {'true', '1', 'yes', 'on'}:
            return True
        if normalised in {'false', '0', 'no', 'off'}:
            return False
        raise ValueError(f'{key} must be a boolean')

    @staticmethod
    def _validate_settings(settings: dict[str, object]) -> None:
        if not isinstance(settings.get('username'), str):
            raise ValueError('username must be a string')
        if not isinstance(settings.get('password'), str):
            raise ValueError('password must be a string')
        interval = settings.get('poll_interval_seconds')
        if isinstance(interval, bool) or not isinstance(interval, int) or interval < 15:
            raise ValueError('poll_interval_seconds must be an integer greater than or equal to 15')
        renew_before = settings.get('renew_before_seconds')
        if isinstance(renew_before, bool) or not isinstance(renew_before, int) or renew_before < 0:
            raise ValueError('renew_before_seconds must be a non-negative integer')
        if not isinstance(settings.get('auto_renew_enabled'), bool):
            raise ValueError('auto_renew_enabled must be a boolean')

    @staticmethod
    def _credentials_configured(settings: dict[str, object]) -> bool:
        username = str(settings['username']).strip()
        password = str(settings['password'])
        return bool(username and password)

    @staticmethod
    def _container_id(value: object) -> int | str:
        if isinstance(value, bool) or not isinstance(value, (int, str)):
            raise ValueError('DESC 容器编号格式错误')
        if isinstance(value, str):
            if not value.strip().isdigit():
                raise ValueError('DESC 容器编号格式错误')
            return int(value)
        return value

    @staticmethod
    def _coerce_seconds(value: object) -> int:
        if isinstance(value, bool):
            raise ValueError('DESC 剩余时间格式错误')
        if isinstance(value, int):
            seconds = value
        elif isinstance(value, float) and value.is_integer():
            seconds = int(value)
        elif isinstance(value, str) and value.strip().isdigit():
            seconds = int(value.strip())
        else:
            raise ValueError('DESC 剩余时间格式错误')
        if seconds < 0:
            raise ValueError('DESC 剩余时间不能小于零')
        return seconds

    @staticmethod
    def _format_duration(seconds: int) -> str:
        hours, remainder = divmod(seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        return f'{hours:02d}:{minutes:02d}:{seconds:02d}'

    def _read_renewal_state(self, renewal_key: str) -> dict[str, object]:
        with self.lock:
            return dict(self.renewal_states.get(renewal_key, {}))

    def _write_renewal_state(
        self,
        renewal_key: str,
        state: dict[str, object],
    ) -> None:
        with self.lock:
            previous = self.renewal_states.get(renewal_key, {})
            updated = dict(previous)
            updated.update(state)
            self.renewal_states[renewal_key] = updated

    @staticmethod
    def _renewal_is_due(state: dict[str, object]) -> bool:
        last_attempt_at = state.get('last_attempt_at')
        if not isinstance(last_attempt_at, datetime):
            return True
        elapsed = datetime.now(timezone.utc) - last_attempt_at
        return elapsed.total_seconds() >= RENEWAL_RETRY_COOLDOWN_SECONDS

    def _clear_auth_locked(self) -> None:
        self.token = None
        self.user_id = None
        self.authenticated = False

    def _set_error(self, detail: str) -> None:
        with self.lock:
            self.last_error = detail
            self.updated_at = self._now()

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()


def create_plugin(
    plugin_root: Path,
    config_store: Any,
    process_registry: object,
) -> ColdescPlugin:
    del process_registry
    return ColdescPlugin(plugin_root, config_store)
