#!/usr/bin/env python3
"""
Script de Inicio del Sistema de Grid Trading
Ejecutar con: python start_system.py
"""

import asyncio
import argparse
import sys
from pathlib import Path

# Agregar directorio actual al path
sys.path.insert(0, str(Path(__file__).parent))

from main_orchestrator import TradingSystemOrchestrator
from config_loader import ConfigLoader
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def initialize_system(config_file: str):
    """
    Inicialización completa del sistema
    """
    logger.info("=" * 80)
    logger.info("INICIALIZACIÓN DEL SISTEMA DE GRID TRADING")
    logger.info("=" * 80)
    
    # Cargar configuración
    config_loader = ConfigLoader(config_file)
    exchange_config = config_loader.get_exchange_config()
    
    # Crear sistema
    system = TradingSystemOrchestrator(config_file=config_file)
    
    # Inicializar con credenciales
    await system.initialize(
        api_key=exchange_config.get('api_key'),
        secret=exchange_config.get('secret')
    )
    
    return system


async def first_training(system: TradingSystemOrchestrator):
    """
    Primer entrenamiento completo (full optimization)
    """
    logger.info("\n" + "=" * 80)
    logger.info("ENTRENAMIENTO INICIAL (COMPLETO)")
    logger.info("=" * 80)
    
    await system.retrain_model(quick_mode=False)
    
    logger.info("\n✓ Entrenamiento inicial completado")


async def run_prediction_and_execution(system: TradingSystemOrchestrator):
    """
    Ejecuta predicción y estrategia de trading
    """
    logger.info("\n" + "=" * 80)
    logger.info("PREDICCIÓN Y EJECUCIÓN")
    logger.info("=" * 80)
    
    await system.execute_trading_strategy()
    
    logger.info("\n✓ Estrategia ejecutada")


async def daily_cycle(config_file: str):
    """
    Ciclo diario completo (para cron job)
    """
    logger.info("=" * 80)
    logger.info("CICLO DIARIO AUTOMÁTICO")
    logger.info("=" * 80)
    
    system = await initialize_system(config_file)
    
    try:
        await system.run_daily_cycle()
        
    except Exception as e:
        logger.error(f"❌ Error en ciclo diario: {e}")
        logger.exception("Stack trace:")
        raise
    
    finally:
        await system.shutdown()


async def interactive_mode(config_file: str):
    """
    Modo interactivo para testing y desarrollo
    """
    system = await initialize_system(config_file)
    
    while True:
        print("\n" + "=" * 60)
        print("SISTEMA DE GRID TRADING - MODO INTERACTIVO")
        print("=" * 60)
        print("\nOpciones:")
        print("1. Entrenar modelo (completo)")
        print("2. Re-entrenar modelo (rápido)")
        print("3. Predecir régimen actual")
        print("4. Ejecutar estrategia")
        print("5. Actualizar datos")
        print("6. Ver estado del grid")
        print("7. Ciclo diario completo")
        print("0. Salir")
        
        choice = input("\nSeleccionar opción: ").strip()
        
        try:
            if choice == '1':
                await system.retrain_model(quick_mode=False)
            
            elif choice == '2':
                await system.retrain_model(quick_mode=True)
            
            elif choice == '3':
                await system.predict_current_regime()
            
            elif choice == '4':
                await system.execute_trading_strategy()
            
            elif choice == '5':
                await system.daily_update()
            
            elif choice == '6':
                bot = system.execution_bot
                print(f"\n📊 Estado del Grid:")
                print(f"  Régimen actual: {bot.current_regime}")
                print(f"  Grid activo: {'Sí' if bot.current_grid is not None else 'No'}")
                if bot.grid_start_time:
                    from datetime import datetime
                    hours = (datetime.now() - bot.grid_start_time).seconds / 3600
                    print(f"  Tiempo activo: {hours:.1f} horas")
                print(f"  Órdenes abiertas: {len(bot.open_orders)}")
            
            elif choice == '7':
                await system.run_daily_cycle()
            
            elif choice == '0':
                logger.info("Cerrando sistema...")
                break
            
            else:
                print("❌ Opción inválida")
        
        except Exception as e:
            logger.error(f"Error: {e}")
            logger.exception("Stack trace:")
    
    await system.shutdown()


def main():
    """
    Punto de entrada principal
    """
    parser = argparse.ArgumentParser(
        description='Sistema de Grid Trading con Machine Learning'
    )
    
    parser.add_argument(
        '--config',
        type=str,
        default='config.yaml',
        help='Ruta al archivo de configuración (default: config.yaml)'
    )
    
    parser.add_argument(
        '--mode',
        type=str,
        choices=['init', 'train', 'predict', 'execute', 'daily', 'interactive'],
        default='interactive',
        help='Modo de operación'
    )
    
    args = parser.parse_args()
    
    # Verificar que existe archivo de configuración
    if not Path(args.config).exists():
        logger.error(f"❌ Archivo de configuración no encontrado: {args.config}")
        logger.info("\nCrear archivo desde config_template.yaml")
        sys.exit(1)
    
    # Ejecutar según modo
    try:
        if args.mode == 'init':
            # Solo inicialización
            asyncio.run(initialize_system(args.config))
            print("\n✓ Sistema inicializado correctamente")
        
        elif args.mode == 'train':
            # Inicializar y entrenar
            async def train_only():
                system = await initialize_system(args.config)
                await first_training(system)
                await system.shutdown()
            
            asyncio.run(train_only())
        
        elif args.mode == 'predict':
            # Solo predicción
            async def predict_only():
                system = await initialize_system(args.config)
                await system.predict_current_regime()
                await system.shutdown()
            
            asyncio.run(predict_only())
        
        elif args.mode == 'execute':
            # Predicción + ejecución
            async def execute_only():
                system = await initialize_system(args.config)
                await run_prediction_and_execution(system)
                await system.shutdown()
            
            asyncio.run(execute_only())
        
        elif args.mode == 'daily':
            # Ciclo diario completo (para cron)
            asyncio.run(daily_cycle(args.config))
        
        elif args.mode == 'interactive':
            # Modo interactivo
            asyncio.run(interactive_mode(args.config))
    
    except KeyboardInterrupt:
        logger.info("\n\nInterrumpido por usuario")
        sys.exit(0)
    
    except Exception as e:
        logger.error(f"\n❌ Error fatal: {e}")
        logger.exception("Stack trace:")
        sys.exit(1)


if __name__ == "__main__":
    main()