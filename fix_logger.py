import re

with open('euroscope/utils/logger.py', 'r', encoding='utf-8') as f:
    content = f.read()

new_block = """    primp_logger = logging.getLogger('primp')
    primp_logger.setLevel(logging.CRITICAL)
    primp_logger.propagate = False
    
    primp_impersonate = logging.getLogger('primp.impersonate')
    primp_impersonate.setLevel(logging.CRITICAL)
    primp_impersonate.propagate = False"""

old_block = """    logging.getLogger('primp').setLevel(logging.ERROR)
    logging.getLogger('primp.impersonate').setLevel(logging.ERROR)"""

content = content.replace(old_block, new_block)

with open('euroscope/utils/logger.py', 'w', encoding='utf-8') as f:
    f.write(content)
print("Updated logger.py")
