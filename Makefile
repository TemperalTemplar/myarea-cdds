up:
	docker compose up -d --build

down:
	docker compose down

logs:
	docker compose logs -f web

shell:
	docker compose exec web bash

db-init:
	docker compose exec web flask db init

db-migrate:
	docker compose exec web flask db migrate -m "$(msg)"

db-upgrade:
	docker compose exec web flask db upgrade

db-stamp:
	docker compose exec web flask db stamp head

create-tables:
	docker compose exec web python -c "\
from app import create_app, db; \
app = create_app(); \
app.app_context().push(); \
db.create_all(); \
print('Tables created.')"

make-admin:
	@echo "Usage: docker compose exec web python -c \"\
from app import create_app, db; from app.models import User; \
app = create_app(); app.app_context().push(); \
u = User.query.filter_by(username='$(user)').first(); \
u.is_admin = True; db.session.commit(); print('Done.')\""

connect-network:
	docker network connect myarea_shared_net myarea_cdds_web
	docker network connect myarea_shared_net myarea_cdds_nginx

restart:
	docker compose restart web nginx
