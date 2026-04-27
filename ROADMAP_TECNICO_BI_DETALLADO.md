# 🛠️ ROADMAP TÉCNICO: IMPLEMENTACIÓN DE MEJORAS BI

**Documento Complementario al Informe de Análisis**

---

## PARTE 1: FASE 1 - MVP ENTERPRISE (Semanas 1-10)

### 📅 Timeline

```
Semana 1-2   │ Setup + Prototipado
Semana 3-5   │ Mobile + Responsive
Semana 5-7   │ Visualización Avanzada
Semana 7-9   │ Colaboración + Data Governance
Semana 9-10  │ Testing + Optimización
```

---

## 1. MOBILE ANALYTICS (4-6 semanas)

### 1.1 Componentes

```
Frontend Web (React)
├── Responsive Dashboards
│   ├── CSS Grid responsive
│   ├── Mobile-first design
│   └── Touch-optimized controls
├── PWA Support
│   ├── Service Workers
│   ├── Offline mode (Dexie.js)
│   └── App Shell architecture
└── Adaptive UI
    ├── Breakpoints: 320px, 480px, 768px, 1024px
    └── Touch gestures (swipe, pinch)

Mobile App (Optional React Native)
├── Expo
├── React Navigation
├── Redux Persist (offline)
└── Native modules (biometric auth)
```

### 1.2 Tareas Específicas

```
SEMANA 1-2: Setup & Infrastructure
├── [ ] Crear branch `feature/mobile-support`
├── [ ] Configurar breakpoints Tailwind (mobile-first)
├── [ ] Setup PWA manifest.json
├── [ ] Implementar Service Worker básico
└── [ ] Configure Dexie.js para caché local

SEMANA 3-4: Responsive Components
├── [ ] Audit: identificar componentes no-responsive
├── [ ] Refactorizar Dashboard grid (Mobile)
│   ├── [ ] BIPage → responsive layout
│   ├── [ ] KPI cards → stacked en mobile
│   └── [ ] Charts → adaptable size
├── [ ] Form inputs → touch-friendly (48px min)
├── [ ] Navigation → hamburger menu en mobile
└── [ ] Testing en iOS Safari + Chrome Android

SEMANA 5: PWA & Offline
├── [ ] Implementar Service Worker
│   ├── [ ] Cache-first strategy para assets
│   ├── [ ] Network-first para API calls
│   └── [ ] Stale-while-revalidate para datos
├── [ ] Dexie.js setup
│   ├── [ ] Sincronización de dashboards guardadas
│   ├── [ ] Queue de cambios pending
│   └── [ ] Conflict resolution
├── [ ] App Shell architecture
├── [ ] Manifest.json + icons
└── [ ] Testing offline scenarios

SEMANA 6: Native App (Optional)
├── [ ] Setup Expo project
├── [ ] React Navigation setup
├── [ ] Replicate main screens
├── [ ] BiometricAuth integration
└── [ ] Build APK/IPA
```

### 1.3 Código Base

**tailwind.config.js** (actualizar):
```javascript
module.exports = {
  content: ['./src/**/*.{js,jsx,ts,tsx}'],
  theme: {
    screens: {
      'xs': '320px',   // NEW
      'sm': '480px',   // NEW
      'md': '768px',
      'lg': '1024px',
      'xl': '1280px',
      '2xl': '1536px',
    },
    extend: {
      spacing: {
        'touch': '48px', // MIN touch target
      }
    }
  },
  plugins: [],
}
```

**BIPage.jsx** (mobile-aware):
```jsx
export default function BIPage() {
  const isMobile = useMediaQuery('(max-width: 768px)');
  
  return (
    <div className="grid gap-4 md:gap-6">
      {/* Header adaptable */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-2 md:gap-4">
        <KPICard title="Revenue" value="€1.2M" />
        {/* Más cards */}
      </div>
      
      {/* Main chart - full width en mobile */}
      <div className="col-span-full">
        <ResponsiveChart data={chartData} />
      </div>
      
      {/* Sidebar - collapse en mobile */}
      {!isMobile && (
        <aside className="hidden lg:block">
          {/* Filtros */}
        </aside>
      )}
    </div>
  );
}
```

**service-worker.js** (nuevo):
```javascript
const CACHE_NAME = 'contecflow-v1';
const API_CACHE = 'contecflow-api-v1';

// Install
self.addEventListener('install', e => {
  e.waitUntil(
    caches.open(CACHE_NAME)
      .then(cache => cache.addAll([
        '/',
        '/index.html',
        '/app.js',
        '/styles.css'
      ]))
  );
  self.skipWaiting();
});

// Fetch Strategy: Network first, fallback to cache
self.addEventListener('fetch', e => {
  const { request } = e;
  
  if (request.url.includes('/api/')) {
    // API: Network first
    e.respondWith(
      fetch(request)
        .then(response => {
          const responseClone = response.clone();
          caches.open(API_CACHE).then(cache => {
            cache.put(request, responseClone);
          });
          return response;
        })
        .catch(() => caches.match(request))
    );
  } else {
    // Assets: Cache first
    e.respondWith(
      caches.match(request)
        .then(response => response || fetch(request))
    );
  }
});
```

---

## 2. VISUALIZACIÓN AVANZADA (8-10 semanas)

### 2.1 Stack Nuevo

**Instalaciones**:
```bash
npm install d3 vega vega-lite apache-echarts plotly.js
npm install @visx/visx d3-plugins-geo d3-contour d3-sankey
npm install visx @visx/xychart @visx/axis @visx/shape @visx/tooltip
```

### 2.2 Nuevos Tipos de Gráficos

```javascript
// Chart types registry
const CHART_TYPES = {
  // Existing
  'bar': BarChart,
  'line': LineChart,
  'pie': PieChart,
  
  // NEW - D3
  'sankey': SankeyChart,
  'sunburst': SunburstChart,
  'treemap': TreemapChart,
  'network': NetworkChart,
  'dendrogram': DendrogramChart,
  
  // NEW - ECharts
  'gauge': GaugeChart,
  '3d_bar': Chart3DBar,
  'heatmap': HeatmapChart,
  'candlestick': CandlestickChart,
  'funnel': FunnelChart,
  'graph': GraphChart,
  
  // NEW - Plotly
  'box': BoxPlotChart,
  'violin': ViolinChart,
  'scatter_3d': Scatter3DChart,
  'surface': SurfaceChart,
};
```

### 2.3 Ejemplo: Sankey (Flujo de Dinero)

**SankeyChart.jsx**:
```jsx
import React, { useMemo } from 'react';
import { Sankey, Sink, Source, Link, Node } from 'd3-sankey';

export function SankeyChart({ data, width, height }) {
  const sankey = useMemo(() => {
    // Transformar data: { nodes: [...], links: [...] }
    // links: { source, target, value }
    return new Sankey()
      .nodeWidth(15)
      .nodePadding(50)
      .extent([[1, 1], [width - 1, height - 6]]);
  }, [width, height]);

  const { nodes, links } = useMemo(() => {
    return sankey({
      nodes: data.nodes.map((d, i) => ({ ...d, index: i })),
      links: data.links.map(d => ({
        ...d,
        source: data.nodes.findIndex(n => n.id === d.source),
        target: data.nodes.findIndex(n => n.id === d.target)
      }))
    });
  }, [data]);

  return (
    <svg width={width} height={height}>
      {/* Render links */}
      <g stroke="#555" strokeOpacity="0.5">
        {links.map((link, i) => (
          <path
            key={i}
            d={linkPath(link)}
            fill="none"
            stroke={colorScale(link.value)}
            strokeWidth={link.width}
          />
        ))}
      </g>
      
      {/* Render nodes */}
      {nodes.map((node, i) => (
        <g key={i}>
          <rect
            x={node.x0}
            y={node.y0}
            width={node.x1 - node.x0}
            height={node.y1 - node.y0}
            fill={colorScale(node.value)}
          />
          <text x={node.x0 + 5} y={node.y0 + 5}>
            {node.name}
          </text>
        </g>
      ))}
    </svg>
  );
}
```

### 2.4 Ejemplo: Heatmap (Matrices de Datos)

**HeatmapChart.jsx**:
```jsx
import * as d3 from 'd3';

export function HeatmapChart({ data, width, height }) {
  // data: { rows, cols, values: [[...], [...]] }
  
  const cellWidth = width / data.cols.length;
  const cellHeight = height / data.rows.length;
  
  const colorScale = d3.scaleLinear()
    .domain(d3.extent(data.values.flat()))
    .range(['blue', 'red']);

  return (
    <svg width={width} height={height}>
      {data.values.map((row, i) =>
        row.map((value, j) => (
          <rect
            key={`${i}-${j}`}
            x={j * cellWidth}
            y={i * cellHeight}
            width={cellWidth}
            height={cellHeight}
            fill={colorScale(value)}
          />
        ))
      )}
    </svg>
  );
}
```

### 2.5 Componente Contenedor

**DynamicChart.jsx** (dispatcher):
```jsx
import { useMemo } from 'react';
import * as Charts from './charts';

export function DynamicChart({ type, data, config = {} }) {
  const width = config.width || 800;
  const height = config.height || 400;

  const ChartComponent = useMemo(() => {
    const ComponentMap = {
      'bar': Charts.BarChart,
      'line': Charts.LineChart,
      'sankey': Charts.SankeyChart,
      'sunburst': Charts.SunburstChart,
      'treemap': Charts.TreemapChart,
      'heatmap': Charts.HeatmapChart,
      'gauge': Charts.GaugeChart,
      '3d_bar': Charts.Chart3DBar,
      'network': Charts.NetworkChart,
      // ... más tipos
    };
    return ComponentMap[type] || Charts.BarChart;
  }, [type]);

  return (
    <div className="chart-container">
      <ChartComponent 
        data={data} 
        width={width} 
        height={height}
        {...config}
      />
    </div>
  );
}
```

### 2.6 Plan de Implementación

```
SEMANA 1-2: Infrastructure
├── [ ] Setup D3 + ECharts
├── [ ] Crear structure: /src/charts/
├── [ ] DynamicChart dispatcher component
└── [ ] Test harness con data fake

SEMANA 3-4: Core Charts
├── [ ] Sankey (priority: $$$ flow)
├── [ ] Sunburst (hierarchy)
├── [ ] Treemap (space visualization)
├── [ ] Heatmap (2D matrices)
└── [ ] Network graph (relationships)

SEMANA 5-6: Advanced Charts
├── [ ] Box Plot (distributions)
├── [ ] Gauge (KPIs)
├── [ ] 3D Scatter
├── [ ] Funnel
└── [ ] Candlestick (time series)

SEMANA 7-8: Integration
├── [ ] Integrar en Report Builder
├── [ ] Integrar en Analytics Query
├── [ ] Agregar a Chart Picker UI
└── [ ] Documentation

SEMANA 9-10: Optimization
├── [ ] Performance tuning (large datasets)
├── [ ] Accessibility (ARIA labels)
├── [ ] Dark mode support
├── [ ] Testing completo
```

---

## 3. COLABORACIÓN EN REPORTES (4-6 semanas)

### 3.1 Esquema de Base de Datos

```sql
-- Tabla de comments
CREATE TABLE dashboard_comments (
  id UUID PRIMARY KEY,
  dashboard_id UUID REFERENCES dashboards(id),
  user_id UUID REFERENCES users(id),
  content TEXT NOT NULL,
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP,
  resolved_at TIMESTAMP,
  mention_ids UUID[] DEFAULT '{}', -- @mentions
  INDEX ON (dashboard_id, created_at DESC)
);

-- Tabla de versioning
CREATE TABLE dashboard_versions (
  id UUID PRIMARY KEY,
  dashboard_id UUID REFERENCES dashboards(id),
  version INT NOT NULL,
  config JSONB NOT NULL,
  changed_by UUID REFERENCES users(id),
  change_log TEXT,
  created_at TIMESTAMP,
  UNIQUE(dashboard_id, version),
  INDEX ON (dashboard_id, created_at DESC)
);

-- Tabla de sharing
CREATE TABLE dashboard_shares (
  id UUID PRIMARY KEY,
  dashboard_id UUID REFERENCES dashboards(id),
  user_id UUID REFERENCES users(id),
  permission ENUM('view', 'edit', 'admin'),
  created_at TIMESTAMP,
  shared_by UUID REFERENCES users(id),
  INDEX ON (user_id, dashboard_id),
  UNIQUE(dashboard_id, user_id)
);

-- Notificaciones
CREATE TABLE dashboard_notifications (
  id UUID PRIMARY KEY,
  user_id UUID REFERENCES users(id),
  dashboard_id UUID REFERENCES dashboards(id),
  type ENUM('comment', 'share', 'edited', 'mention'),
  related_user_id UUID REFERENCES users(id),
  content TEXT,
  read BOOLEAN DEFAULT FALSE,
  created_at TIMESTAMP,
  INDEX ON (user_id, read, created_at DESC)
);
```

### 3.2 Backend Service

**collaboration_service.py**:
```python
from sqlalchemy.orm import Session
from datetime import datetime
from typing import List

class CollaborationService:
    
    def add_comment(
        self,
        dashboard_id: str,
        user_id: str,
        content: str,
        mentions: List[str] = None,
        db: Session = None
    ) -> DashboardComment:
        """Add comment to dashboard"""
        comment = DashboardComment(
            dashboard_id=dashboard_id,
            user_id=user_id,
            content=content,
            mention_ids=mentions or []
        )
        db.add(comment)
        db.commit()
        
        # Notificar @mentioned users
        if mentions:
            self._notify_mentions(comment, mentions, db)
        
        # Broadcast to other users via WebSocket
        self._broadcast_comment(comment)
        
        return comment
    
    def create_version(
        self,
        dashboard_id: str,
        config: dict,
        user_id: str,
        change_log: str = None,
        db: Session = None
    ) -> DashboardVersion:
        """Save dashboard version"""
        last_version = db.query(DashboardVersion)\
            .filter_by(dashboard_id=dashboard_id)\
            .order_by(DashboardVersion.version.desc())\
            .first()
        
        next_version = (last_version.version + 1) if last_version else 1
        
        version = DashboardVersion(
            dashboard_id=dashboard_id,
            version=next_version,
            config=config,
            changed_by=user_id,
            change_log=change_log
        )
        db.add(version)
        db.commit()
        
        # Notify collaborators
        self._notify_dashboard_change(dashboard_id, user_id, db)
        
        return version
    
    def share_dashboard(
        self,
        dashboard_id: str,
        user_id: str,
        permission: str,
        shared_by: str,
        db: Session = None
    ):
        """Share dashboard with user"""
        share = DashboardShare(
            dashboard_id=dashboard_id,
            user_id=user_id,
            permission=permission,
            shared_by=shared_by
        )
        db.add(share)
        db.commit()
        
        # Notification
        self._notify_share(dashboard_id, user_id, shared_by, db)
    
    def get_comments(
        self,
        dashboard_id: str,
        db: Session = None
    ) -> List[DashboardComment]:
        """Get all comments on dashboard"""
        return db.query(DashboardComment)\
            .filter_by(dashboard_id=dashboard_id)\
            .order_by(DashboardComment.created_at.desc())\
            .all()
    
    def get_versions(
        self,
        dashboard_id: str,
        db: Session = None
    ) -> List[DashboardVersion]:
        """Get version history"""
        return db.query(DashboardVersion)\
            .filter_by(dashboard_id=dashboard_id)\
            .order_by(DashboardVersion.version.desc())\
            .all()
    
    def rollback_version(
        self,
        dashboard_id: str,
        version: int,
        user_id: str,
        db: Session = None
    ):
        """Restore previous version"""
        old_version = db.query(DashboardVersion)\
            .filter_by(dashboard_id=dashboard_id, version=version)\
            .first()
        
        if not old_version:
            raise ValueError("Version not found")
        
        # Save new version with rollback
        self.create_version(
            dashboard_id=dashboard_id,
            config=old_version.config,
            user_id=user_id,
            change_log=f"Rollback to v{version}",
            db=db
        )
```

### 3.3 Frontend Components

**DashboardComments.jsx**:
```jsx
import { useState, useEffect } from 'react';
import { format } from 'date-fns';

export function DashboardComments({ dashboardId, userId }) {
  const [comments, setComments] = useState([]);
  const [newComment, setNewComment] = useState('');
  const [mentions, setMentions] = useState([]);

  useEffect(() => {
    loadComments();
    subscribeToComments();
  }, [dashboardId]);

  const loadComments = async () => {
    const res = await fetch(`/api/dashboards/${dashboardId}/comments`);
    setComments(await res.json());
  };

  const handleAddComment = async () => {
    const res = await fetch(
      `/api/dashboards/${dashboardId}/comments`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          content: newComment,
          mentions
        })
      }
    );
    
    const comment = await res.json();
    setComments([comment, ...comments]);
    setNewComment('');
    setMentions([]);
  };

  const subscribeToComments = () => {
    const ws = new WebSocket(
      `ws://localhost:8000/ws/dashboards/${dashboardId}/comments`
    );
    
    ws.onmessage = (event) => {
      const newComment = JSON.parse(event.data);
      setComments([newComment, ...comments]);
    };
  };

  return (
    <div className="comments-section">
      <h3>Comments</h3>
      
      {/* Comment input */}
      <div className="comment-input">
        <textarea
          value={newComment}
          onChange={(e) => setNewComment(e.target.value)}
          placeholder="Add a comment... (use @ to mention)"
        />
        <button onClick={handleAddComment}>Post</button>
      </div>
      
      {/* Comment list */}
      <div className="comments-list">
        {comments.map(comment => (
          <div key={comment.id} className="comment">
            <div className="comment-header">
              <strong>{comment.user.name}</strong>
              <span className="timestamp">
                {format(new Date(comment.created_at), 'MMM d, HH:mm')}
              </span>
            </div>
            <p>{comment.content}</p>
          </div>
        ))}
      </div>
    </div>
  );
}
```

---

## 4. DATA GOVERNANCE AUDIT (4-6 semanas)

### 4.1 Schema

```sql
-- Audit trail
CREATE TABLE audit_log (
  id UUID PRIMARY KEY,
  org_id UUID NOT NULL,
  user_id UUID REFERENCES users(id),
  entity_type ENUM('dashboard', 'report', 'metric', 'dataset'),
  entity_id UUID,
  action ENUM('view', 'create', 'edit', 'delete', 'export', 'share'),
  before_state JSONB,
  after_state JSONB,
  ip_address INET,
  user_agent TEXT,
  timestamp TIMESTAMP DEFAULT NOW(),
  INDEX ON (org_id, timestamp DESC),
  INDEX ON (user_id, timestamp DESC),
  INDEX ON (entity_type, entity_id)
);

-- Data lineage
CREATE TABLE data_lineage (
  id UUID PRIMARY KEY,
  source_table TEXT,
  target_table TEXT,
  transformation_sql TEXT,
  created_by UUID,
  created_at TIMESTAMP DEFAULT NOW(),
  UNIQUE(source_table, target_table)
);

-- Field-level sensitivity
CREATE TABLE field_sensitivity (
  id UUID PRIMARY KEY,
  dataset_id UUID,
  field_name TEXT,
  sensitivity_level ENUM('public', 'internal', 'confidential', 'restricted'),
  pii_fields TEXT[],
  requires_approval BOOLEAN DEFAULT FALSE,
  UNIQUE(dataset_id, field_name)
);
```

### 4.2 Service

**governance_service.py**:
```python
class GovernanceService:
    
    def log_access(
        self,
        user_id: str,
        entity_type: str,
        entity_id: str,
        action: str,
        request: Request,
        db: Session = None
    ):
        """Log all BI access"""
        audit = AuditLog(
            org_id=get_user_org(user_id),
            user_id=user_id,
            entity_type=entity_type,
            entity_id=entity_id,
            action=action,
            ip_address=request.client.host,
            user_agent=request.headers.get('user-agent')
        )
        db.add(audit)
        db.commit()
    
    def get_access_history(
        self,
        user_id: str = None,
        entity_id: str = None,
        org_id: str = None,
        days: int = 30,
        db: Session = None
    ):
        """Get audit trail"""
        query = db.query(AuditLog)
        
        if org_id:
            query = query.filter_by(org_id=org_id)
        if user_id:
            query = query.filter_by(user_id=user_id)
        if entity_id:
            query = query.filter_by(entity_id=entity_id)
        
        cutoff = datetime.now() - timedelta(days=days)
        query = query.filter(AuditLog.timestamp >= cutoff)
        
        return query.order_by(AuditLog.timestamp.desc()).all()
    
    def track_lineage(
        self,
        source: str,
        target: str,
        sql: str,
        user_id: str,
        db: Session = None
    ):
        """Track data transformation"""
        lineage = DataLineage(
            source_table=source,
            target_table=target,
            transformation_sql=sql,
            created_by=user_id
        )
        db.add(lineage)
        db.commit()
    
    def get_lineage_for_table(self, table_name: str, db: Session = None):
        """Data lineage: upstream"""
        return db.query(DataLineage)\
            .filter_by(target_table=table_name)\
            .all()
```

---

## PARTE 2: FASE 2 - ADVANCED ANALYTICS (Semanas 11-24)

### 📅 Timeline Simplificada

```
Semana 11-13  │ ML Pipeline Setup
Semana 14-17  │ 5 Conectores (Salesforce, HubSpot, Jira, Stripe, Xero)
Semana 18-20  │ Real-time Streaming (WebSocket + Kafka)
Semana 21-23  │ Report Builder Advanced
Semana 24     │ Integration + Testing
```

---

## 5. ML INTEGRADO (8-10 semanas)

### 5.1 Modelos a Implementar

```python
# 1. Forecasting (Prophet)
from fbprophet import Prophet

def forecast_revenue(historical_data: pd.DataFrame, periods: int = 90):
    """Predict revenue 90 days ahead"""
    df = historical_data.rename(columns={
        'date': 'ds',
        'revenue': 'y'
    })
    
    model = Prophet(
        yearly_seasonality=True,
        monthly_seasonality=True,
        daily_seasonality=False
    )
    model.fit(df)
    
    future = model.make_future_dataframe(periods=periods)
    forecast = model.predict(future)
    
    return forecast[['ds', 'yhat', 'yhat_lower', 'yhat_upper']]

# 2. Anomaly Detection (Isolation Forest)
from sklearn.ensemble import IsolationForest

def detect_anomalies(data: pd.DataFrame, contamination: float = 0.1):
    """Detect unusual patterns"""
    iso_forest = IsolationForest(contamination=contamination)
    data['anomaly'] = iso_forest.fit_predict(data[['value']])
    
    return data[data['anomaly'] == -1]

# 3. Churn Prediction (LightGBM)
import lightgbm as lgb

def predict_churn(customer_features: pd.DataFrame):
    """Predict customer churn"""
    model = lgb.LGBMClassifier(n_estimators=100)
    # ... training code
    predictions = model.predict_proba(customer_features)
    
    return predictions[:, 1]  # Probability of churn
```

### 5.2 ML Service

**ml_service.py**:
```python
import pandas as pd
import numpy as np
from prophet import Prophet
from sklearn.ensemble import IsolationForest
import lightgbm as lgb
import pickle
import os

class MLService:
    def __init__(self):
        self.models_dir = '/var/contecflow/models'
        os.makedirs(self.models_dir, exist_ok=True)
    
    def forecast_revenue(self, historical_df, periods=90):
        """Forecast revenue for next N periods"""
        df = historical_df.rename(columns={'date': 'ds', 'amount': 'y'})
        
        model = Prophet(yearly_seasonality=True)
        model.fit(df)
        
        future = model.make_future_dataframe(periods=periods)
        forecast = model.predict(future)
        
        # Save for later
        self._save_model(model, 'revenue_forecast')
        
        return {
            'forecast': forecast[['ds', 'yhat', 'yhat_lower', 'yhat_upper']].to_dict(),
            'rmse': self._calculate_rmse(model, df)
        }
    
    def detect_anomalies(self, data_df, threshold_std=3):
        """Detect anomalous records"""
        iso_forest = IsolationForest(contamination=0.05)
        predictions = iso_forest.fit_predict(data_df[['value']])
        
        data_df['is_anomaly'] = predictions == -1
        anomalies = data_df[data_df['is_anomaly']].to_dict('records')
        
        return {
            'anomalies': anomalies,
            'count': len(anomalies),
            'pct': len(anomalies) / len(data_df)
        }
    
    def predict_project_success(self, project_features):
        """Predict if project will be successful (on-time, within budget)"""
        model = self._load_model('project_success')
        
        if model is None:
            # Train new model
            model = lgb.LGBMClassifier(n_estimators=100)
            # ... training logic
            self._save_model(model, 'project_success')
        
        predictions = model.predict_proba(project_features)
        return predictions[:, 1]
    
    def _save_model(self, model, name):
        path = f'{self.models_dir}/{name}.pkl'
        with open(path, 'wb') as f:
            pickle.dump(model, f)
    
    def _load_model(self, name):
        path = f'{self.models_dir}/{name}.pkl'
        if not os.path.exists(path):
            return None
        with open(path, 'rb') as f:
            return pickle.load(f)
```

---

## 6. CONECTORES (10-12 semanas)

### 6.1 Framework de Conectores

```python
# Base connector interface
class BaseConnector(ABC):
    def __init__(self, credentials: Dict):
        self.credentials = credentials
    
    @abstractmethod
    def authenticate(self):
        pass
    
    @abstractmethod
    def get_data(self, query: str) -> pd.DataFrame:
        pass
    
    @abstractmethod
    def transform_to_fact(self, data: pd.DataFrame) -> pd.DataFrame:
        pass

# Salesforce Connector
class SalesforceConnector(BaseConnector):
    def __init__(self, credentials: Dict):
        super().__init__(credentials)
        from simple_salesforce import Salesforce
        self.sf = Salesforce(
            username=credentials['username'],
            password=credentials['password'],
            security_token=credentials['security_token']
        )
    
    def authenticate(self):
        self.sf.describe()  # Test connection
    
    def get_data(self, query: str) -> pd.DataFrame:
        results = self.sf.query_all(query)
        return pd.DataFrame(results['records'])
    
    def transform_to_fact(self, data: pd.DataFrame) -> pd.DataFrame:
        # Transform into our star schema
        return data.rename(columns={
            'Amount': 'revenue',
            'CloseDate': 'date',
            'StageName': 'stage'
        })

# HubSpot Connector
class HubSpotConnector(BaseConnector):
    def __init__(self, credentials: Dict):
        super().__init__(credentials)
        import hubspot
        self.client = hubspot.Client(
            access_token=credentials['api_key']
        )
    
    def get_data(self, object_type: str) -> pd.DataFrame:
        # Get all contacts/deals/etc
        results = self.client.crm.objects.basic_api.get_page(
            object_type,
            limit=100
        )
        return pd.DataFrame([obj.properties for obj in results.results])

# Stripe Connector
class StripeConnector(BaseConnector):
    def __init__(self, credentials: Dict):
        super().__init__(credentials)
        import stripe
        stripe.api_key = credentials['api_key']
    
    def get_data(self, resource: str) -> pd.DataFrame:
        # Get charges, customers, etc
        if resource == 'charges':
            charges = stripe.Charge.list(limit=100)
            return pd.DataFrame([c.to_dict() for c in charges])
```

### 6.2 ETL Pipeline para Conectores

**connector_etl_service.py**:
```python
@app.task(bind=True)
def sync_connector_data(self, connector_id: str, org_id: str):
    """Celery task: Sync external data"""
    connector_config = get_connector_config(connector_id, org_id)
    connector_class = get_connector_class(connector_config['type'])
    
    connector = connector_class(connector_config['credentials'])
    connector.authenticate()
    
    # Extract
    raw_data = connector.get_data(connector_config['query'])
    
    # Transform
    fact_data = connector.transform_to_fact(raw_data)
    
    # Load
    insert_to_olap(fact_data, connector_config['target_table'])
    
    # Log
    log_sync(connector_id, len(fact_data), 'success')
```

### 6.3 Scheduler (Airflow)

```python
# dags/connectors.py
from airflow import DAG
from airflow.operators.python import PythonOperator
from datetime import datetime, timedelta

default_args = {
    'owner': 'contecflow',
    'retries': 2,
    'retry_delay': timedelta(minutes=5)
}

with DAG(
    'sync_external_connectors',
    default_args=default_args,
    schedule_interval='0 * * * *',  # Hourly
    start_date=datetime(2024, 1, 1)
) as dag:
    
    sync_salesforce = PythonOperator(
        task_id='sync_salesforce',
        python_callable=sync_connector_task,
        op_kwargs={'connector_id': 'salesforce', 'org_id': '{{ var.json.org_id }}'}
    )
    
    sync_hubspot = PythonOperator(
        task_id='sync_hubspot',
        python_callable=sync_connector_task,
        op_kwargs={'connector_id': 'hubspot', 'org_id': '{{ var.json.org_id }}'}
    )
    
    [sync_salesforce, sync_hubspot]
```

---

## 7. REAL-TIME STREAMING (6-8 semanas)

### 7.1 Arquitectura

```
┌──────────────────────────────────┐
│ Event Sources                    │
├──────────────────────────────────┤
│ Imputations, Project Updates     │
│ Client Activities, etc           │
└──────────┬───────────────────────┘
           │
        ┌──▼──┐
        │Event│
        │Bus  │ (Kafka/Redis)
        └──┬──┘
           │
    ┌──────┴───────┐
    │              │
┌───▼────────┐  ┌─▼───────────┐
│DuckDB OLAP │  │Client Browser│
│(via Faust) │  │(via WS)      │
└────────────┘  └──────────────┘
```

### 7.2 Implementación con Redis Streams

**stream_processor.py**:
```python
import redis
import json
from typing import Callable

class StreamProcessor:
    def __init__(self, redis_url: str):
        self.redis = redis.from_url(redis_url)
        self.handlers = {}
    
    def register_handler(self, event_type: str, handler: Callable):
        """Register handler for event type"""
        self.handlers[event_type] = handler
    
    def publish_event(self, event_type: str, data: dict):
        """Publish event to stream"""
        event = {
            'type': event_type,
            'data': data,
            'timestamp': time.time()
        }
        self.redis.xadd(
            f'stream:{event_type}',
            {'payload': json.dumps(event)}
        )
    
    def start_consuming(self):
        """Start consuming events"""
        while True:
            for event_type in self.handlers:
                # Read from stream
                messages = self.redis.xread(
                    {f'stream:{event_type}': '$'},
                    block=1000
                )
                
                for stream, data in messages:
                    for msg_id, msg_data in data:
                        event = json.loads(msg_data[b'payload'])
                        
                        # Process
                        handler = self.handlers[event_type]
                        handler(event['data'])
                        
                        # Acknowledge
                        self.redis.xack(stream, 'group', msg_id)

# Usage
processor = StreamProcessor('redis://localhost:6379')

@processor.register_handler('imputation.created')
def handle_new_imputation(data):
    # Update OLAP in real-time
    insert_to_duckdb(data)
    
    # Notify connected clients
    broadcast_to_websockets('imputation_updated', data)

processor.start_consuming()
```

### 7.3 WebSocket Server (FastAPI)

**websocket_server.py**:
```python
from fastapi import WebSocket, WebSocketDisconnect
import asyncio
import json

class ConnectionManager:
    def __init__(self):
        self.active_connections = {}
    
    async def connect(self, websocket: WebSocket, user_id: str):
        await websocket.accept()
        if user_id not in self.active_connections:
            self.active_connections[user_id] = []
        self.active_connections[user_id].append(websocket)
    
    async def disconnect(self, websocket: WebSocket, user_id: str):
        self.active_connections[user_id].remove(websocket)
    
    async def broadcast_personal(self, user_id: str, message: dict):
        if user_id in self.active_connections:
            for connection in self.active_connections[user_id]:
                try:
                    await connection.send_json(message)
                except:
                    pass

manager = ConnectionManager()

@app.websocket("/ws/analytics/{user_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: str):
    await manager.connect(websocket, user_id)
    
    try:
        while True:
            data = await websocket.receive_text()
            # Echo or process
            await websocket.send_text(f"Echo: {data}")
    except WebSocketDisconnect:
        await manager.disconnect(websocket, user_id)

# Broadcast updates from stream processor
def broadcast_to_websockets(event_type: str, data: dict):
    asyncio.create_task(
        manager.broadcast_personal(
            data.get('org_id'),
            {'type': event_type, 'data': data}
        )
    )
```

---

## PARTE 3: DEPLOYMENT Y OPERACIONALIZACIÓN

### 📦 Docker Compose Actualizado

**docker-compose.yml** (ejemplo):
```yaml
version: '3.8'

services:
  # Frontend
  frontend:
    build: ./frontend
    ports:
      - "3000:3000"
    environment:
      REACT_APP_API_URL: http://localhost:8000
      REACT_APP_WS_URL: ws://localhost:8000
    depends_on:
      - backend

  # Backend
  backend:
    build: ./app
    ports:
      - "8000:8000"
    environment:
      DATABASE_URL: postgresql://user:pass@postgres:5432/contecflow
      REDIS_URL: redis://redis:6379
      DUCKDB_PATH: /data/olap.duckdb
      KAFKA_BROKERS: kafka:29092
    volumes:
      - /var/contecflow/data:/data
    depends_on:
      - postgres
      - redis
      - kafka
      - duckdb

  # Kafka (Event streaming)
  kafka:
    image: confluentinc/cp-kafka:latest
    environment:
      KAFKA_BROKER_ID: 1
      KAFKA_ZOOKEEPER_CONNECT: zookeeper:2181
    depends_on:
      - zookeeper

  # Redis
  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"

  # PostgreSQL
  postgres:
    image: postgres:15
    environment:
      POSTGRES_PASSWORD: password
      POSTGRES_DB: contecflow
    volumes:
      - postgres_data:/var/lib/postgresql/data

  # Airflow (Orchestration)
  airflow:
    image: apache/airflow:latest
    ports:
      - "8080:8080"
    environment:
      AIRFLOW_HOME: /airflow
      AIRFLOW__CORE__DAGS_FOLDER: /airflow/dags
    volumes:
      - ./dags:/airflow/dags

volumes:
  postgres_data:
```

---

## CONCLUSIÓN

Este roadmap detallado proporciona:

✅ **Arquitectura clara** para cada componente
✅ **Timeline realista** (18-24 semanas para 3 fases)
✅ **Código base** para iniciar desarrollo inmediatamente
✅ **Stack technológico** moderno y escalable

**Siguientes pasos**:
1. Presentar al equipo de desarrollo
2. Crear tickets JIRA para cada tarea
3. Asignar recursos y DRIs (Directly Responsible Individuals)
4. Ejecutar Fase 1 primero (10 semanas) para MVP

---
