use crate::db::Pool;

pub fn delete_user(id: &str) {}

fn hidden() {}

pub struct UserService;

impl UserService {
    pub fn purge(&self, id: &str) {}
}

#[get("/users")]
async fn list() {}
