from django.urls import path
from . import views

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('insights/', views.ai_insights, name='ai_insights'),
    path('signup/', views.signup, name='signup'),
    path('download-csv/', views.download_csv, name='download_csv'),
]
