"""Provider authorization, independent of browser controls and provider secrets."""
import ipaddress

PREMIUM_ROLES = frozenset({'vip', 'admin', 'owner'})
PROVIDERS = ('qwen', 'chatgpt', 'claude')
PROXY_HEADERS = ('forwarded', 'x-forwarded-for', 'x-forwarded-host', 'x-forwarded-proto',
                 'x-real-ip', 'cf-connecting-ip', 'true-client-ip')


def local_access(request, public_origin=''):
    # Public deployments never inherit local privileges from a loopback proxy.
    # Local operation is restricted to a direct loopback connection and URL.
    if public_origin or any(name in request.headers for name in PROXY_HEADERS):
        return False
    if request.url.hostname not in {'localhost', '127.0.0.1', '::1'}:
        return False
    try:
        return bool(request.client and ipaddress.ip_address(request.client.host).is_loopback)
    except ValueError:
        return False


def model_access(request, identity, public_origin=''):
    user = identity.get('user') or {}
    role = user.get('role', 'member') if identity.get('account_id') else 'guest'
    local = local_access(request, public_origin)
    privileged = role in PREMIUM_ROLES and bool(identity.get('account_id')) and not user.get('disabled')
    verified = user.get('auth_provider') != 'email' or bool(user.get('email_verified'))
    premium = (local or privileged) and not user.get('disabled') and (local or verified)
    allowed = list(PROVIDERS) if premium else ['qwen']
    return {'local': local, 'role': role, 'allowed': allowed,
            'reason': 'local' if local else 'role' if premium else 'qwen_only',
            'message': '本机可使用全部已配置模型。' if local else
                       '当前账号可使用全部已配置模型。' if premium else
                       'Qwen 向所有用户开放；ChatGPT 和 Claude 供 VIP、管理员及本机使用。'}


def restrict_capabilities(capabilities, access):
    result = []
    by_id = {item['id']: item for item in capabilities}
    for ident in PROVIDERS:
        item = dict(by_id.get(ident, {'id': ident, 'available': False, 'message': '模型尚未配置。'}))
        permitted = ident in access['allowed']
        item['permitted'] = permitted
        if not permitted:
            item['available'] = False
            item['message'] = '此模型需 VIP、管理员权限，或在本机工作台使用。'
            # Do not reveal local provider configuration to unauthorized visitors.
            for key in list(item):
                if key not in {'id', 'name', 'available', 'permitted', 'message'}:
                    item.pop(key)
        result.append(item)
    return result
