package api

import "net/http"

func DeleteUser(id string) {}

func hidden() {}

type UserService struct{}

func (s *UserService) Purge(id string) {}

func mount(r Router) {
	r.HandleFunc("/users", DeleteUser)
}
