"""
Cliente da API REST do Supabase: CRUD, sincronização e relatórios.

Extraído da tela de administração, que misturava as chamadas HTTP com a
montagem de widgets. Aqui não há nada de interface — as telas consomem estes
métodos e cuidam só de exibir.
"""

import sqlite3
from datetime import datetime, timedelta

import requests

from club272 import config

SUPABASE_URL = config.SUPABASE_URL
SUPABASE_KEY = config.SUPABASE_KEY


class SupabaseManager:
    """Gerenciador completo de operações CRUD no Supabase"""
    
    def __init__(self):
        self.headers = {
            'apikey': SUPABASE_KEY,
            'Authorization': f'Bearer {SUPABASE_KEY}',
            'Content-Type': 'application/json'
        }
        self.connected = False
        self.test_connection()
    
    def test_connection(self):
        """Testa conexão com Supabase"""
        try:
            response = requests.get(
                f"{SUPABASE_URL}/rest/v1/",
                headers=self.headers,
                timeout=10
            )
            self.connected = response.status_code in [200, 401, 403]
            return self.connected
        except:
            self.connected = False
            return False
    
    # ===== OPERAÇÕES CRUD =====
    
    def get_all_users(self):
        """Obtém todos os usuários do Supabase"""
        try:
            response = requests.get(
                f"{SUPABASE_URL}/rest/v1/{config.SUPABASE_TABLE}",
                headers=self.headers
            )
            if response.status_code == 200:
                return response.json()
            return []
        except Exception as e:
            print(f"Erro ao buscar usuários: {e}")
            return []
    
    def get_user_by_id(self, user_id):
        """Busca usuário específico por ID"""
        try:
            response = requests.get(
                f"{SUPABASE_URL}/rest/v1/{config.SUPABASE_TABLE}?id=eq.{user_id}",
                headers=self.headers
            )
            if response.status_code == 200:
                users = response.json()
                return users[0] if users else None
            return None
        except Exception as e:
            print(f"Erro ao buscar usuário: {e}")
            return None
    
    def create_user(self, user_data):
        """Cria novo usuário no Supabase"""
        try:
            response = requests.post(
                f"{SUPABASE_URL}/rest/v1/{config.SUPABASE_TABLE}",
                headers={**self.headers, 'Prefer': 'return=representation'},
                json=user_data
            )
            return response.status_code in [200, 201, 204]
        except Exception as e:
            print(f"Erro ao criar usuário: {e}")
            return False
    
    def update_user(self, user_id, update_data):
        """Atualiza usuário existente"""
        try:
            response = requests.patch(
                f"{SUPABASE_URL}/rest/v1/{config.SUPABASE_TABLE}?id=eq.{user_id}",
                headers=self.headers,
                json=update_data
            )
            return response.status_code in [200, 204]
        except Exception as e:
            print(f"Erro ao atualizar usuário: {e}")
            return False
    
    def delete_user(self, user_id):
        """Exclui usuário do Supabase"""
        try:
            response = requests.delete(
                f"{SUPABASE_URL}/rest/v1/{config.SUPABASE_TABLE}?id=eq.{user_id}",
                headers=self.headers
            )
            return response.status_code in [200, 204]
        except Exception as e:
            print(f"Erro ao excluir usuário: {e}")
            return False
    
    def sync_from_local_db(self, db_path=None):
        """Sincroniza dados do banco local para o Supabase"""
        try:
            conn = sqlite3.connect(db_path or config.DB_PATH)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute("SELECT * FROM usuarios")
            local_users = cursor.fetchall()
            
            synced = 0
            errors = 0
            
            for local_user in local_users:
                user_dict = dict(local_user)
                
                supabase_data = {
                    'id': user_dict['id'],
                    'name': user_dict['name'],
                    'group': user_dict.get('group_name', ''),
                    'phone': user_dict.get('phone', ''),
                    'total_attendance': user_dict.get('total_attendance', 0),
                    'last_attendance_time': user_dict.get('last_attendance_time')
                }
                
                # Verificar se já existe
                existing = self.get_user_by_id(user_dict['id'])
                
                if existing:
                    # Atualizar
                    if self.update_user(user_dict['id'], supabase_data):
                        synced += 1
                    else:
                        errors += 1
                else:
                    # Criar novo
                    if self.create_user(supabase_data):
                        synced += 1
                    else:
                        errors += 1
            
            conn.close()
            return {'synced': synced, 'errors': errors, 'total': len(local_users)}
            
        except Exception as e:
            print(f"Erro na sincronização: {e}")
            return {'synced': 0, 'errors': 1, 'total': 0, 'error': str(e)}
    
    def sync_to_local_db(self, db_path=None):
        """Sincroniza dados do Supabase para o banco local"""
        try:
            supabase_users = self.get_all_users()

            conn = sqlite3.connect(db_path or config.DB_PATH)
            cursor = conn.cursor()
            
            synced = 0
            errors = 0
            
            for user in supabase_users:
                try:
                    cursor.execute('''
                        INSERT OR REPLACE INTO usuarios 
                        (id, name, group_name, phone, total_attendance, last_attendance_time, sync_status)
                        VALUES (?, ?, ?, ?, ?, ?, 'synced')
                    ''', (
                        user.get('id'),
                        user.get('name'),
                        user.get('group'),
                        user.get('phone'),
                        user.get('total_attendance', 0),
                        user.get('last_attendance_time')
                    ))
                    synced += 1
                except Exception as e:
                    print(f"Erro ao sincronizar usuário {user.get('id')}: {e}")
                    errors += 1
            
            conn.commit()
            conn.close()
            return {'synced': synced, 'errors': errors, 'total': len(supabase_users)}
            
        except Exception as e:
            print(f"Erro na sincronização: {e}")
            return {'synced': 0, 'errors': 1, 'total': 0, 'error': str(e)}
    
    # ===== RELATÓRIOS E ANÁLISES =====
    
    def get_monthly_report(self, year=None, month=None):
        """Gera relatório mensal de presenças"""
        if year is None:
            year = datetime.now().year
        if month is None:
            month = datetime.now().month
        
        users = self.get_all_users()
        report = []
        
        for user in users:
            last_attendance = user.get('last_attendance_time')
            if last_attendance:
                try:
                    dt = datetime.fromisoformat(last_attendance.replace('Z', '+00:00'))
                    if dt.year == year and dt.month == month:
                        report.append({
                            'id': user.get('id'),
                            'name': user.get('name'),
                            'group': user.get('group', ''),
                            'last_attendance': dt,
                            'total_attendance': user.get('total_attendance', 0)
                        })
                except:
                    continue
        
        return report
    
    def get_event_report(self, event_name):
        """Gera relatório por evento específico"""
        users = self.get_all_users()
        event_users = []
        
        for user in users:
            user_event = user.get('event', '')
            if event_name.lower() in str(user_event).lower():
                event_users.append({
                    'id': user.get('id'),
                    'name': user.get('name'),
                    'group': user.get('group', ''),
                    'total_attendance': user.get('total_attendance', 0),
                    'last_attendance': user.get('last_attendance_time')
                })
        
        return event_users
    
    def get_yearly_report(self, year=None):
        """Gera relatório anual"""
        if year is None:
            year = datetime.now().year
        
        users = self.get_all_users()
        report = []
        
        for user in users:
            last_attendance = user.get('last_attendance_time')
            if last_attendance:
                try:
                    dt = datetime.fromisoformat(last_attendance.replace('Z', '+00:00'))
                    if dt.year == year:
                        report.append({
                            'id': user.get('id'),
                            'name': user.get('name'),
                            'group': user.get('group', ''),
                            'last_attendance': dt,
                            'total_attendance': user.get('total_attendance', 0),
                            'month': dt.month
                        })
                except:
                    continue
        
        return report
    
    def get_group_stats(self):
        """Estatísticas por grupo"""
        users = self.get_all_users()
        groups = {}
        
        for user in users:
            group = user.get('group', 'Sem Grupo')
            attendance = user.get('total_attendance', 0)
            
            if group not in groups:
                groups[group] = {
                    'count': 0,
                    'total_attendance': 0,
                    'users': []
                }
            
            groups[group]['count'] += 1
            groups[group]['total_attendance'] += attendance
            groups[group]['users'].append({
                'id': user.get('id'),
                'name': user.get('name'),
                'attendance': attendance
            })
        
        # Ordenar por total de presenças
        sorted_groups = sorted(
            groups.items(),
            key=lambda x: x[1]['total_attendance'],
            reverse=True
        )
        
        return dict(sorted_groups)
    
    def get_top_members(self, limit=10):
        """Top membros com mais presenças"""
        users = self.get_all_users()
        users_with_attendance = [
            {
                'id': u.get('id'),
                'name': u.get('name'),
                'group': u.get('group', ''),
                'attendance': u.get('total_attendance', 0),
                'last_attendance': u.get('last_attendance_time')
            }
            for u in users
            if u.get('total_attendance', 0) > 0
        ]
        
        sorted_users = sorted(
            users_with_attendance,
            key=lambda x: x['attendance'],
            reverse=True
        )
        
        return sorted_users[:limit]
    
    def get_attendance_trend(self, days=30):
        """Tendência de presenças nos últimos dias"""
        users = self.get_all_users()
        today = datetime.now()
        trend = {}
        
        for i in range(days):
            date = today - timedelta(days=i)
            date_str = date.strftime('%Y-%m-%d')
            trend[date_str] = 0
        
        for user in users:
            last_attendance = user.get('last_attendance_time')
            if last_attendance:
                try:
                    dt = datetime.fromisoformat(last_attendance.replace('Z', '+00:00'))
                    date_str = dt.strftime('%Y-%m-%d')
                    if date_str in trend:
                        trend[date_str] += 1
                except:
                    continue
        
        return trend
